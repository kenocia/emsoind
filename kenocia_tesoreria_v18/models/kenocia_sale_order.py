# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    advance_payment_ids = fields.One2many(
        comodel_name='kenocia.advance.payment',
        inverse_name='sale_order_id',
        string='Adelantos',
    )
    advance_count = fields.Integer(
        string='Cantidad de adelantos',
        compute='_compute_advance_count',
    )
    advance_amount_total = fields.Monetary(
        string='Total anticipado',
        compute='_compute_advance_amounts',
        store=True,
        currency_field='currency_id',
    )
    advance_residual = fields.Monetary(
        string='Saldo anticipos',
        compute='_compute_advance_amounts',
        store=True,
        currency_field='currency_id',
    )
    amount_due = fields.Monetary(
        string='Total a cobrar',
        compute='_compute_advance_amounts',
        store=True,
        currency_field='currency_id',
        help='Total de la orden menos anticipos registrados disponibles.',
    )

    @api.depends('advance_payment_ids.state')
    def _compute_advance_count(self):
        active_states = ('confirmed', 'partially_applied', 'fully_applied')
        for order in self:
            order.advance_count = len(order.advance_payment_ids.filtered(
                lambda adv: adv.state in active_states,
            ))

    @api.depends(
        'amount_total',
        'advance_payment_ids.amount',
        'advance_payment_ids.amount_residual',
        'advance_payment_ids.state',
    )
    def _compute_advance_amounts(self):
        active_states = ('confirmed', 'partially_applied', 'fully_applied')
        for order in self:
            advances = order.advance_payment_ids.filtered(
                lambda adv: adv.state in active_states,
            )
            order.advance_amount_total = sum(advances.mapped('amount'))
            order.advance_residual = sum(advances.mapped('amount_residual'))
            order.amount_due = max(
                order.amount_total - order.advance_residual,
                0.0,
            )

    def action_view_advances(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Adelantos de la orden'),
            'res_model': 'kenocia.advance.payment',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {
                'default_sale_order_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_advance_type': 'customer',
                'default_currency_id': self.currency_id.id,
            },
        }
