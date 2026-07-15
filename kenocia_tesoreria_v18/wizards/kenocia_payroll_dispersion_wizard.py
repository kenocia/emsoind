# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3
"""Escenario 3 — Dispersión de nómina vía banco.

Lote de nómina aprobado/completo → un pago por empleado que salda su neto
por pagar → agrupados en account.batch.payment → cuenta puente → archivo del
banco (Fase 2). El pago confirma la salida de efectivo (marca payslips 'paid').
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class KenociaPayrollDispersionWizard(models.TransientModel):
    _name = 'kenocia.payroll.dispersion.wizard'
    _description = 'Wizard — Dispersión de nómina'

    company_id = fields.Many2one(
        comodel_name='res.company',
        default=lambda self: self.env.company,
    )
    payslip_run_id = fields.Many2one(
        comodel_name='hr.payslip.run',
        string='Lote de nómina',
        required=True,
        domain="[('state', 'in', ('02_close', '03_paid')), ('company_id', '=', company_id)]",
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario banco',
        required=True,
        domain="[('type', '=', 'bank')]",
    )
    payment_date = fields.Date(
        string='Fecha de depósito',
        required=True,
        default=fields.Date.context_today,
    )
    memo = fields.Char(
        string='Concepto',
        default='Pago de nómina',
    )
    bank_format = fields.Selection(
        related='journal_id.kenocia_bank_format',
        string='Formato banco',
        readonly=True,
        help='Se toma automáticamente del diario bancario seleccionado. '
             'Configúrelo en el diario (Tesorería → Configuración → Diarios).',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        compute='_compute_currency',
        store=True,
    )
    amount_total = fields.Monetary(
        string='Total a depositar',
        compute='_compute_summary',
        currency_field='currency_id',
    )
    employee_count = fields.Integer(
        string='Empleados',
        compute='_compute_summary',
    )

    @api.depends('journal_id', 'company_id')
    def _compute_currency(self):
        for wiz in self:
            wiz.currency_id = (
                wiz.journal_id.currency_id
                or wiz.journal_id.company_id.currency_id
                or self.env.company.currency_id
            )

    @api.depends('payslip_run_id')
    def _compute_summary(self):
        for wiz in self:
            slips = wiz._kenocia_eligible_payslips()
            wiz.amount_total = sum(slips.mapped('net_wage'))
            wiz.employee_count = len(slips)

    def _kenocia_eligible_payslips(self):
        self.ensure_one()
        if not self.payslip_run_id:
            return self.env['hr.payslip']
        return self.payslip_run_id.slip_ids.filtered(
            lambda s: s.state == 'validated'
            and s.move_id
            and s.move_id.state == 'posted',
        )

    def action_confirm(self):
        self.ensure_one()
        slips = self._kenocia_eligible_payslips()
        if not slips:
            raise UserError(_(
                'No hay nóminas elegibles en el lote. Deben estar validadas, '
                'con asiento publicado y sin pagar.',
            ))

        engine = self.env['kenocia.dispersion.engine']
        specs = []
        no_bank = []
        for slip in slips:
            employee = slip.employee_id
            partner = employee.work_contact_id
            payable_lines = slip.move_id.line_ids.filtered(
                lambda l: l.partner_id == partner
                and l.account_id.reconcile
                and not l.reconciled
                and l.balance < 0,
            )
            if not payable_lines:
                # Neto ya conciliado (pagado por otra vía): se omite.
                continue
            if not employee.bank_account_ids:
                no_bank.append(employee.display_name)
                continue
            accounts = payable_lines.account_id
            if len(accounts) != 1:
                raise UserError(_(
                    'El empleado %(name)s tiene líneas por pagar en varias '
                    'cuentas; revise la configuración contable de la nómina.',
                    name=employee.display_name,
                ))
            allocations = [
                (line, abs(line.amount_residual)) for line in payable_lines
            ]
            specs.append({
                'partner': partner,
                'partner_type': 'supplier',
                'payment_type': 'outbound',
                'account': accounts,
                'allocations': allocations,
                'memo': self.memo,
                'slip': slip,
            })

        if no_bank:
            raise UserError(_(
                'Empleados sin cuenta bancaria asignada (no se puede dispersar):'
                '\n- %(list)s',
                list='\n- '.join(no_bank),
            ))
        if not specs:
            raise UserError(_(
                'No hay netos pendientes por dispersar en este lote '
                '(es posible que ya estén pagados).',
            ))

        result = engine.kenocia_run_dispersion(
            [{k: v for k, v in s.items() if k != 'slip'} for s in specs],
            self.journal_id, self.payment_date,
            memo=self.memo, group_into_batch=True, batch_label=self.memo,
            batch_tesoreria_type='transferencia_banco',
        )

        paid_slips = self.env['hr.payslip'].union(*[s['slip'] for s in specs])
        paid_slips.action_payslip_paid()
        paid_slips.write({'paid_date': self.payment_date})

        batch = result['batch']
        if batch:
            batch.write({
                'kenocia_source': 'payroll',
                'kenocia_bank_format': self.bank_format or False,
            })
            return {
                'type': 'ir.actions.act_window',
                'name': _('Lote de dispersión de nómina'),
                'res_model': 'account.batch.payment',
                'res_id': batch.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pagos de nómina'),
            'res_model': 'account.payment',
            'domain': [('id', 'in', result['payments'].ids)],
            'view_mode': 'list,form',
            'target': 'current',
        }
