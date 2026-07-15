# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class KenociaPettyCashLine(models.Model):
    _name = 'kenocia.petty.cash.line'
    _description = 'Anticipo de Caja Chica'
    _order = 'date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    petty_cash_id = fields.Many2one(
        comodel_name='kenocia.petty.cash',
        string='Fondo',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    date = fields.Date(
        string='Fecha entrega',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    employee_id = fields.Many2one(
        comodel_name='res.partner',
        string='Empleado',
        required=True,
        tracking=True,
    )
    description = fields.Char(
        string='Concepto',
        required=True,
        tracking=True,
    )
    amount = fields.Monetary(
        string='Monto anticipo',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('delivered', 'Entregado'),
            ('settled', 'Liquidado'),
            ('cancelled', 'Cancelado'),
        ],
        default='draft',
        required=True,
        tracking=True,
    )
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura SAR',
        readonly=True,
        copy=False,
        tracking=True,
    )
    amount_invoice = fields.Monetary(
        string='Monto factura',
        currency_field='currency_id',
        readonly=True,
        copy=False,
    )
    amount_returned = fields.Monetary(
        string='Vuelto devuelto',
        currency_field='currency_id',
        readonly=True,
        copy=False,
        default=0.0,
    )
    amount_pending = fields.Monetary(
        string='Pendiente',
        compute='_compute_amount_pending',
        currency_field='currency_id',
    )
    settlement_payment_id = fields.Many2one(
        comodel_name='account.payment',
        string='Pago liquidación',
        readonly=True,
        copy=False,
    )
    move_settlement_id = fields.Many2one(
        comodel_name='account.move',
        string='Asiento liquidación',
        readonly=True,
        copy=False,
    )
    settlement_date = fields.Date(
        string='Fecha liquidación',
        readonly=True,
        copy=False,
        tracking=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='petty_cash_id.currency_id',
        store=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='petty_cash_id.company_id',
        store=True,
    )

    _sql_constraints = [
        (
            'positive_amount',
            'CHECK(amount > 0)',
            'El monto del anticipo debe ser mayor a cero.',
        ),
    ]

    @api.depends('amount', 'amount_invoice', 'state')
    def _compute_amount_pending(self):
        for line in self:
            if line.state == 'settled':
                line.amount_pending = 0.0
            elif line.state == 'delivered':
                line.amount_pending = line.amount - (line.amount_invoice or 0.0)
            else:
                line.amount_pending = line.amount

    @api.constrains('amount')
    def _check_positive_amount(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(_(
                    'El monto del anticipo debe ser mayor a cero.',
                ))

    def action_confirm_delivery(self):
        """Entrega física de efectivo — sin asiento contable."""
        for line in self:
            if not line.petty_cash_id._kenocia_user_can_manage_petty_cash():
                raise AccessError(_(
                    'No tiene permiso para entregar anticipos de caja chica.',
                ))
            if not line.employee_id:
                raise UserError(_('Debe seleccionar un empleado.'))
            if not line.amount or line.amount <= 0:
                raise UserError(_('El monto del anticipo debe ser mayor a cero.'))
            if line.petty_cash_id.state != 'open':
                raise UserError(_('El fondo de caja chica no está abierto.'))
            if line.state != 'draft':
                raise UserError(_('Este anticipo ya fue procesado.'))
            if line.amount > line.petty_cash_id.amount_available:
                raise UserError(_(
                    'Monto supera el saldo disponible del fondo '
                    '(%(avail)s).',
                    avail=line.currency_id.format(line.petty_cash_id.amount_available),
                ))
            line.write({'state': 'delivered'})
            line.message_post(
                body=_(
                    'Anticipo entregado a <b>%(emp)s</b>. '
                    'Monto: <b>%(amount)s</b>. '
                    'Saldo disponible del fondo: <b>%(avail)s</b>.',
                    emp=line.employee_id.display_name,
                    amount=line.currency_id.format(line.amount),
                    avail=line.currency_id.format(line.petty_cash_id.amount_available),
                ),
                subtype_xmlid='mail.mt_note',
            )
            line.petty_cash_id.message_post(
                body=_(
                    'Anticipo entregado: %(emp)s — %(concept)s — %(amount)s.',
                    emp=line.employee_id.display_name,
                    concept=line.description,
                    amount=line.currency_id.format(line.amount),
                ),
                subtype_xmlid='mail.mt_note',
            )
        return True

    def action_settle_with_invoice(self):
        self.ensure_one()
        if self.state != 'delivered':
            raise UserError(_('Solo se pueden liquidar anticipos en estado Entregado.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Liquidar anticipo con factura SAR'),
            'res_model': 'kenocia.petty.cash.settlement',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_id': self.id,
            },
        }

    def action_settle(self):
        """Alias de compatibilidad con vistas anteriores."""
        return self.action_settle_with_invoice()

    def action_cancel_line(self):
        for line in self:
            if line.state == 'settled':
                raise UserError(_('No se puede cancelar un anticipo liquidado.'))
            line.write({'state': 'cancelled'})
            line.message_post(
                body=_('Anticipo cancelado.'),
                subtype_xmlid='mail.mt_note',
            )
        return True

    def action_view_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Factura SAR'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_id.id,
        }

    def action_view_settlement_payment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pago liquidación'),
            'res_model': 'account.payment',
            'view_mode': 'form',
            'res_id': self.settlement_payment_id.id,
        }
