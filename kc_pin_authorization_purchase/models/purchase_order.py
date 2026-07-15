# -*- coding: utf-8 -*-

from odoo import models


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'kc.pin.authorization.mixin']

    def button_confirm(self):
        # Enganche mínimo: si hay una regla activa para (purchase.order,
        # 'confirm') cuyo dominio aplica a estas órdenes, se exige el PIN antes
        # de confirmar. El alcance se controla desde Ajustes.
        action = self._kc_pin_guard('confirm', 'button_confirm')
        if action:
            return action
        return super().button_confirm()
