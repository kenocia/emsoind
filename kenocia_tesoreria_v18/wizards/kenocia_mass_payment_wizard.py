# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3
"""Escenario 1 — Pago/Cobro masivo de un solo contacto.

Un contacto → un pago (cheque/transferencia/efectivo con correlativo) →
varias facturas con monto parcial editable → publica y concilia.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

TREASURY_TYPES = [
    ('cheque', 'Cheque'),
    ('deposito', 'Depósito'),
    ('debito', 'Débito'),
    ('credito', 'Crédito'),
    ('transferencia', 'Transferencia'),
    ('transferencia_banco', 'Transferencia Bancaria'),
    ('efectivo', 'Efectivo'),
]


class KenociaMassPaymentWizard(models.TransientModel):
    _name = 'kenocia.mass.payment.wizard'
    _description = 'Wizard — Pago/Cobro masivo de un contacto'

    operation = fields.Selection(
        selection=[('cxc', 'Cobro (CXC)'), ('cxp', 'Pago (CXP)')],
        string='Operación',
        required=True,
        default=lambda self: self.env.context.get('default_operation', 'cxp'),
    )
    payment_type = fields.Selection(
        selection=[('inbound', 'Entrante'), ('outbound', 'Saliente')],
        string='Tipo de pago',
        compute='_compute_payment_meta',
        store=True,
    )
    partner_type = fields.Selection(
        selection=[('customer', 'Cliente'), ('supplier', 'Proveedor')],
        string='Tipo de contacto',
        compute='_compute_payment_meta',
        store=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Contacto',
        required=True,
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario (banco/efectivo)',
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    tesoreria_type = fields.Selection(
        selection=TREASURY_TYPES,
        string='Tipo tesorería',
        help='Si se indica, asigna el correlativo de tesorería al pago.',
    )
    payment_date = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.context_today,
    )
    memo = fields.Char(string='Concepto')
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        compute='_compute_currency',
        store=True,
    )
    line_ids = fields.One2many(
        comodel_name='kenocia.mass.payment.wizard.line',
        inverse_name='wizard_id',
        string='Documentos a pagar',
    )
    amount_total = fields.Monetary(
        string='Total del pago',
        compute='_compute_amount_total',
        currency_field='currency_id',
    )

    @api.depends('operation')
    def _compute_payment_meta(self):
        for wiz in self:
            if wiz.operation == 'cxc':
                wiz.payment_type = 'inbound'
                wiz.partner_type = 'customer'
            else:
                wiz.payment_type = 'outbound'
                wiz.partner_type = 'supplier'

    @api.depends('journal_id', 'company_id')
    def _compute_currency(self):
        for wiz in self:
            wiz.currency_id = (
                wiz.journal_id.currency_id
                or wiz.journal_id.company_id.currency_id
                or self.env.company.currency_id
            )

    company_id = fields.Many2one(
        comodel_name='res.company',
        default=lambda self: self.env.company,
    )

    @api.depends('line_ids.amount_to_pay', 'line_ids.include')
    def _compute_amount_total(self):
        for wiz in self:
            wiz.amount_total = sum(
                line.amount_to_pay
                for line in wiz.line_ids.filtered('include')
            )

    @api.onchange('partner_id', 'operation', 'journal_id')
    def _onchange_load_lines(self):
        self.line_ids = [(5, 0, 0)]
        if not self.partner_id:
            return
        lines = self._kenocia_search_open_lines()
        self.line_ids = [
            (0, 0, {
                'move_line_id': line.id,
                'amount_to_pay': abs(line.amount_residual),
                'include': True,
            })
            for line in lines
        ]

    def _kenocia_search_open_lines(self):
        self.ensure_one()
        account_type = (
            'asset_receivable' if self.operation == 'cxc'
            else 'liability_payable'
        )
        return self.env['account.move.line'].search([
            ('partner_id', '=', self.partner_id.id),
            ('account_id.account_type', '=', account_type),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('amount_residual', '!=', 0.0),
            ('company_id', '=', self.company_id.id),
        ], order='date_maturity, id')

    def action_confirm(self):
        self.ensure_one()
        lines = self.line_ids.filtered(
            lambda l: l.include and l.amount_to_pay > 0,
        )
        if not lines:
            raise UserError(_('Seleccione al menos un documento con monto a pagar.'))

        engine = self.env['kenocia.dispersion.engine']
        allocations = []
        accounts = set()
        for line in lines:
            ml = line.move_line_id
            engine.kenocia_check_allocation_amount(ml, line.amount_to_pay)
            allocations.append((ml, line.amount_to_pay))
            accounts.add(ml.account_id.id)

        if len(accounts) != 1:
            raise UserError(_(
                'Los documentos seleccionados usan distintas cuentas por '
                'cobrar/pagar; no se pueden saldar con un solo pago.',
            ))

        spec = {
            'partner': self.partner_id,
            'partner_type': self.partner_type,
            'payment_type': self.payment_type,
            'account': lines[0].move_line_id.account_id,
            'allocations': allocations,
            'memo': self.memo,
        }
        result = engine.kenocia_run_dispersion(
            [spec], self.journal_id, self.payment_date,
            memo=self.memo, tesoreria_type=self.tesoreria_type,
            group_into_batch=False,
        )
        payment = result['payments']
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pago generado'),
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
        }


class KenociaMassPaymentWizardLine(models.TransientModel):
    _name = 'kenocia.mass.payment.wizard.line'
    _description = 'Línea wizard pago masivo'

    wizard_id = fields.Many2one(
        comodel_name='kenocia.mass.payment.wizard',
        required=True,
        ondelete='cascade',
    )
    move_line_id = fields.Many2one(
        comodel_name='account.move.line',
        string='Apunte',
        required=True,
    )
    move_id = fields.Many2one(
        related='move_line_id.move_id',
        string='Documento',
    )
    date_maturity = fields.Date(
        related='move_line_id.date_maturity',
        string='Vencimiento',
    )
    currency_id = fields.Many2one(
        related='wizard_id.currency_id',
    )
    amount_residual = fields.Monetary(
        string='Saldo pendiente',
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
                    'El monto a pagar supera el saldo pendiente del documento %(doc)s.',
                    doc=line.move_id.display_name,
                ))
