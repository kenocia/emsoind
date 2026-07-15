# -*- coding: utf-8 -*-

from odoo import models


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'kc.pin.authorization.mixin']

    def action_confirm(self):
        # Enganche mínimo: si hay una regla activa para (sale.order, 'confirm')
        # cuyo dominio aplica a estos pedidos, se exige el PIN antes de
        # confirmar. El alcance se controla desde Ajustes.
        action = self._kc_pin_guard('confirm', 'action_confirm')
        if action:
            return action
        return super().action_confirm()
