# -*- coding: utf-8 -*-

from odoo import models


class StockPicking(models.Model):
    _name = 'stock.picking'
    _inherit = ['stock.picking', 'kc.pin.authorization.mixin']

    def button_validate(self):
        # Enganche mínimo: si hay una regla activa para (stock.picking,
        # 'validate') cuyo dominio aplica a estas transferencias, se exige el
        # PIN antes de validar. Todo el alcance se controla desde Ajustes.
        action = self._kc_pin_guard('validate', 'button_validate')
        if action:
            return action
        return super().button_validate()
