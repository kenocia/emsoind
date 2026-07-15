# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class KenociaPettyCash(models.Model):
    _name = 'kenocia.petty.cash'
    _description = 'Fondo de Caja Chica KENOCIA'
    _order = 'date_from desc, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Nombre del fondo',
        required=True,
        tracking=True,
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario de caja',
        required=True,
        tracking=True,
        domain="[('type', '=', 'cash')]",
    )
    account_bridge_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta puente (tránsito)',
        required=True,
        tracking=True,
        domain="[('account_type', '=', 'liability_payable')]",
    )
    custodian_id = fields.Many2one(
        comodel_name='res.partner',
        string='Custodio',
        required=True,
        tracking=True,
    )
    date_from = fields.Date(
        string='Fecha inicio',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    date_to = fields.Date(
        string='Fecha fin',
        required=True,
        tracking=True,
    )
    amount_authorized = fields.Monetary(
        string='Monto autorizado',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    line_ids = fields.One2many(
        comodel_name='kenocia.petty.cash.line',
        inverse_name='petty_cash_id',
        string='Anticipos entregados',
    )
    recharge_ids = fields.One2many(
        comodel_name='kenocia.petty.cash.recharge',
        inverse_name='petty_cash_id',
        string='Recargas',
    )
    line_count = fields.Integer(
        string='Anticipos',
        compute='_compute_line_count',
    )
    recharge_count = fields.Integer(
        string='Recargas',
        compute='_compute_recharge_count',
    )
    recharge_in_transit_count = fields.Integer(
        string='Recargas en tránsito',
        compute='_compute_recharge_in_transit_count',
    )
    recharge_total = fields.Monetary(
        string='Total recargas',
        compute='_compute_recharge_total',
        store=True,
        currency_field='currency_id',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('open', 'Abierto'),
            ('closed', 'Cerrado'),
            ('cancelled', 'Cancelado'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        default=lambda self: self.env.company,
        required=True,
        index=True,
    )
    notes = fields.Text(string='Observaciones', tracking=True)
    amount_delivered = fields.Monetary(
        string='Entregado a empleados',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
        tracking=True,
    )
    amount_settled = fields.Monetary(
        string='Liquidado con factura',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
        tracking=True,
    )
    amount_pending = fields.Monetary(
        string='Pendiente de liquidar',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
        tracking=True,
    )
    amount_available = fields.Monetary(
        string='Disponible en caja',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
        tracking=True,
    )
    close_physical_amount = fields.Monetary(
        string='Saldo físico al cierre',
        currency_field='currency_id',
        readonly=True,
        copy=False,
    )
    close_difference_amount = fields.Monetary(
        string='Diferencia de arqueo',
        currency_field='currency_id',
        readonly=True,
        copy=False,
    )
    close_return_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Banco de devolución',
        readonly=True,
        copy=False,
    )
    close_move_return_id = fields.Many2one(
        comodel_name='account.move',
        string='Asiento de cierre',
        readonly=True,
        copy=False,
    )
    close_notes = fields.Text(string='Observaciones de cierre', readonly=True, copy=False)
    close_user_id = fields.Many2one(
        comodel_name='res.users',
        string='Cerrado por',
        readonly=True,
        copy=False,
    )
    close_date = fields.Datetime(string='Fecha de cierre', readonly=True, copy=False)

    _sql_constraints = [
        (
            'valid_dates',
            'CHECK(date_to >= date_from)',
            'La fecha fin debe ser mayor o igual a la fecha inicio.',
        ),
        (
            'positive_amount',
            'CHECK(amount_authorized > 0)',
            'El monto autorizado debe ser mayor a cero.',
        ),
    ]

    @api.depends('line_ids')
    def _compute_line_count(self):
        for fund in self:
            fund.line_count = len(fund.line_ids)

    @api.depends('recharge_ids')
    def _compute_recharge_count(self):
        for fund in self:
            fund.recharge_count = len(fund.recharge_ids)

    @api.depends('recharge_ids.state')
    def _compute_recharge_in_transit_count(self):
        for fund in self:
            fund.recharge_in_transit_count = len(
                fund.recharge_ids.filtered(lambda r: r.state == 'in_transit'),
            )

    @api.depends('recharge_ids.state', 'recharge_ids.amount')
    def _compute_recharge_total(self):
        for fund in self:
            fund.recharge_total = sum(
                recharge.amount
                for recharge in fund.recharge_ids
                if recharge.state == 'received'
            )

    @api.depends(
        'amount_authorized',
        'recharge_ids.amount',
        'recharge_ids.state',
        'line_ids.amount',
        'line_ids.state',
        'line_ids.amount_returned',
    )
    def _compute_amounts(self):
        for fund in self:
            recharge_total = sum(
                recharge.amount for recharge in fund.recharge_ids
                if recharge.state == 'received'
            )
            base = fund.amount_authorized + recharge_total
            delivered = sum(
                line.amount for line in fund.line_ids
                if line.state in ('delivered', 'settled')
            )
            settled = sum(
                line.amount for line in fund.line_ids
                if line.state == 'settled'
            )
            returned = sum(
                line.amount_returned for line in fund.line_ids
                if line.state == 'settled'
            )
            fund.amount_delivered = delivered
            fund.amount_settled = settled
            fund.amount_pending = delivered - settled
            fund.amount_available = base - delivered + returned

    @api.model
    def _kenocia_user_can_manage_petty_cash(self):
        user = self.env.user
        return (
            user.has_group('kenocia_tesoreria_v18.group_tesoreria_custodian')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_supervisor')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_admin')
        )

    def action_open_fund(self):
        for fund in self:
            if not fund._kenocia_user_can_manage_petty_cash():
                raise AccessError(_(
                    'Solo custodios, supervisores o administradores pueden abrir fondos.',
                ))
            if fund.state != 'draft':
                raise UserError(_('Solo fondos en borrador pueden abrirse.'))
            if not fund.account_bridge_id.reconcile:
                raise UserError(_(
                    'La cuenta puente %(account)s no tiene activada la opción '
                    '"Permitir conciliación". Actívela en el Plan de Cuentas.',
                    account=fund.account_bridge_id.display_name,
                ))
            fund.write({'state': 'open'})
            fund.message_post(
                body=_(
                    'Fondo <b>%(name)s</b> abierto. '
                    'Monto autorizado: <b>%(amount)s</b>.',
                    name=fund.name,
                    amount=fund.currency_id.format(fund.amount_authorized),
                ),
                subtype_xmlid='mail.mt_note',
            )
        return True

    def action_close_fund(self):
        """Abre wizard de cierre con arqueo y asiento de devolución."""
        self.ensure_one()
        if not self.env.user.has_group(
            'kenocia_tesoreria_v18.group_tesoreria_supervisor',
        ) and not self.env.user.has_group(
            'kenocia_tesoreria_v18.group_tesoreria_admin',
        ):
            raise AccessError(_(
                'Solo supervisores o administradores pueden cerrar fondos.',
            ))
        if self.state != 'open':
            raise UserError(_('Solo fondos abiertos pueden cerrarse.'))
        if self.recharge_in_transit_count:
            raise UserError(_(
                'No se puede cerrar el fondo mientras haya recargas en tránsito.',
            ))
        pending_advances = self.line_ids.filtered(lambda line: line.state == 'delivered')
        if pending_advances:
            names = ', '.join(pending_advances.mapped('employee_id.display_name'))
            raise UserError(_(
                'No se puede cerrar el fondo. Existen %(count)s anticipo(s) '
                'sin liquidar:\n%(names)s\n\n'
                'Liquide todos los anticipos con su factura SAR antes de cerrar.',
                count=len(pending_advances),
                names=names,
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cerrar fondo de caja chica'),
            'res_model': 'kenocia.petty.cash.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_fund_id': self.id,
                'default_amount_physical': self.amount_available,
            },
        }

    def action_register_recharge(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nueva recarga'),
            'res_model': 'kenocia.petty.cash.recharge',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_petty_cash_id': self.id,
            },
        }

    def action_view_recharges(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recargas - %(fund)s', fund=self.name),
            'res_model': 'kenocia.petty.cash.recharge',
            'view_mode': 'list,form',
            'domain': [('petty_cash_id', '=', self.id)],
            'context': {'default_petty_cash_id': self.id},
        }

    def action_view_pending_lines(self):
        self.ensure_one()
        pending = self.line_ids.filtered(lambda line: line.state == 'delivered')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Anticipos pendientes de liquidar'),
            'res_model': 'kenocia.petty.cash.line',
            'view_mode': 'list,form',
            'domain': [('id', 'in', pending.ids)],
        }

    def action_view_all_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Anticipos del fondo'),
            'res_model': 'kenocia.petty.cash.line',
            'view_mode': 'list,form',
            'domain': [('petty_cash_id', '=', self.id)],
            'context': {'default_petty_cash_id': self.id},
        }
