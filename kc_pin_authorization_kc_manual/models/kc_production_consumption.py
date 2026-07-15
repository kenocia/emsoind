# -*- coding: utf-8 -*-

from odoo import models


class KcProductionConsumption(models.Model):
    _name = 'kc.production.consumption'
    _inherit = ['kc.production.consumption', 'kc.pin.authorization.mixin']

    def action_confirm(self):
        # Enganche mínimo: si hay una regla activa para
        # (kc.production.consumption, 'confirm') cuyo dominio aplica, se exige
        # el PIN antes de confirmar el consumo de materia prima.
        action = self._kc_pin_guard('confirm', 'action_confirm')
        if action:
            return action
        return super().action_confirm()

    def action_validate(self):
        # Enganche mínimo: la validación del consumo impacta inventario, por lo
        # que se exige el PIN si hay una regla activa (operación 'validate').
        action = self._kc_pin_guard('validate', 'action_validate')
        if action:
            return action
        return super().action_validate()

    def action_open_reversal_wizard(self):
        # La reversión del consumo genera un movimiento inverso de inventario:
        # se exige el PIN (operación 'reverse') antes de abrir el asistente.
        action = self._kc_pin_guard('reverse', 'action_open_reversal_wizard')
        if action:
            return action
        return super().action_open_reversal_wizard()
