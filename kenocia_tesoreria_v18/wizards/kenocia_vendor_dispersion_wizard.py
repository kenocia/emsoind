# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3
"""Escenario 2 — Dispersión a proveedores vía banco.

Selección multi-proveedor de facturas abiertas (con parciales) → un pago por
proveedor → agrupados en un account.batch.payment → cuenta puente → archivo
del banco (Fase 2).
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class KenociaVendorDispersionWizard(models.TransientModel):
    _name = 'kenocia.vendor.dispersion.wizard'
    _description = 'Wizard — Dispersión a proveedores'

    company_id = fields.Many2one(
        comodel_name='res.company',
        default=lambda self: self.env.company,
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
        default='Dispersión a proveedores',
    )
    bank_format = fields.Selection(
        related='journal_id.kenocia_bank_format',
        string='Formato banco',
        readonly=True,
        help='Se toma automáticamente del diario bancario seleccionado. '
             'Configúrelo en el diario (Tesorería → Configuración → Diarios).',
    )
    partner_ids = fields.Many2many(
        comodel_name='res.partner',
        string='Filtrar proveedores',
        help='Opcional. Si se deja vacío, carga facturas de todos los proveedores.',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        compute='_compute_currency',
        store=True,
    )
    line_ids = fields.One2many(
        comodel_name='kenocia.vendor.dispersion.wizard.line',
        inverse_name='wizard_id',
        string='Facturas a pagar',
    )
    amount_total = fields.Monetary(
        string='Total a depositar',
        compute='_compute_totals',
        currency_field='currency_id',
    )
    line_count = fields.Integer(
        string='Cantidad de líneas',
        compute='_compute_totals',
    )

    @api.depends('journal_id', 'company_id')
    def _compute_currency(self):
        for wiz in self:
            wiz.currency_id = (
                wiz.journal_id.currency_id
                or wiz.journal_id.company_id.currency_id
                or self.env.company.currency_id
            )

    @api.depends('line_ids.amount_to_pay', 'line_ids.include')
    def _compute_totals(self):
        for wiz in self:
            included = wiz.line_ids.filtered('include')
            wiz.amount_total = sum(included.mapped('amount_to_pay'))
            wiz.line_count = len(included)

    def action_load_invoices(self):
        self.ensure_one()
        domain = [
            ('account_id.account_type', '=', 'liability_payable'),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('amount_residual', '!=', 0.0),
            ('company_id', '=', self.company_id.id),
            ('move_id.move_type', 'in', ('in_invoice', 'in_refund')),
        ]
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        lines = self.env['account.move.line'].search(
            domain, order='partner_id, date_maturity, id',
        )
        self.line_ids = [(5, 0, 0)] + [
            (0, 0, {
                'move_line_id': line.id,
                'amount_to_pay': abs(line.amount_residual),
                'include': True,
            })
            for line in lines
        ]
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm(self):
        self.ensure_one()
        lines = self.line_ids.filtered(
            lambda l: l.include and l.amount_to_pay > 0,
        )
        if not lines:
            raise UserError(_('Seleccione al menos una factura con monto a pagar.'))

        engine = self.env['kenocia.dispersion.engine']
        specs_by_partner = {}
        for line in lines:
            ml = line.move_line_id
            engine.kenocia_check_allocation_amount(ml, line.amount_to_pay)
            partner = ml.partner_id
            key = (partner.id, ml.account_id.id)
            spec = specs_by_partner.setdefault(key, {
                'partner': partner,
                'partner_type': 'supplier',
                'payment_type': 'outbound',
                'account': ml.account_id,
                'allocations': [],
                'memo': self.memo,
            })
            spec['allocations'].append((ml, line.amount_to_pay))

        self._kenocia_check_partner_banks(specs_by_partner)

        result = engine.kenocia_run_dispersion(
            list(specs_by_partner.values()), self.journal_id, self.payment_date,
            memo=self.memo, group_into_batch=True,
            batch_label=self.memo,
            batch_tesoreria_type='transferencia_banco',
        )
        batch = result['batch']
        if batch:
            batch.write({
                'kenocia_source': 'vendor',
                'kenocia_bank_format': self.bank_format or False,
            })
            return self._open_batch_action(batch)
        return self._open_payments_action(result['payments'])

    def _kenocia_check_partner_banks(self, specs_by_partner):
        missing = [
            spec['partner'].display_name
            for spec in specs_by_partner.values()
            if not spec['partner'].bank_ids
        ]
        if missing:
            raise UserError(_(
                'Los siguientes proveedores no tienen cuenta bancaria '
                'registrada (necesaria para la dispersión):\n- %(list)s',
                list='\n- '.join(missing),
            ))

    def _open_batch_action(self, batch):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lote de dispersión'),
            'res_model': 'account.batch.payment',
            'res_id': batch.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _open_payments_action(self, payments):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pagos generados'),
            'res_model': 'account.payment',
            'domain': [('id', 'in', payments.ids)],
            'view_mode': 'list,form',
            'target': 'current',
        }


class KenociaVendorDispersionWizardLine(models.TransientModel):
    _name = 'kenocia.vendor.dispersion.wizard.line'
    _description = 'Línea wizard dispersión proveedores'

    wizard_id = fields.Many2one(
        comodel_name='kenocia.vendor.dispersion.wizard',
        required=True,
        ondelete='cascade',
    )
    move_line_id = fields.Many2one(
        comodel_name='account.move.line',
        string='Apunte',
        required=True,
    )
    partner_id = fields.Many2one(
        related='move_line_id.partner_id',
        string='Proveedor',
        store=True,
    )
    move_id = fields.Many2one(
        related='move_line_id.move_id',
        string='Factura',
    )
    date_maturity = fields.Date(
        related='move_line_id.date_maturity',
        string='Vencimiento',
    )
    currency_id = fields.Many2one(
        related='wizard_id.currency_id',
    )
    amount_residual = fields.Monetary(
        string='Saldo',
        compute='_compute_amount_residual',
        currency_field='currency_id',
    )
    amount_to_pay = fields.Monetary(
        string='Monto a pagar',
        currency_field='currency_id',
    )
    include = fields.Boolean(string='Incluir', default=True)

    @api.depends('move_line_id.amount_residual')
    def _compute_amount_residual(self):
        for line in self:
            line.amount_residual = abs(line.move_line_id.amount_residual)

    @api.constrains('amount_to_pay')
    def _check_amount_to_pay(self):
        for line in self:
            if line.amount_to_pay < 0:
                raise UserError(_('El monto a pagar no puede ser negativo.'))
            rounding = (line.currency_id or line.move_line_id.company_currency_id).rounding
            residual = abs(line.move_line_id.amount_residual)
            if float_compare(line.amount_to_pay, residual, precision_rounding=rounding) > 0:
                raise UserError(_(
                    'El monto a pagar supera el saldo de la factura %(doc)s.',
                    doc=line.move_id.display_name,
                ))
