# -*- coding: utf-8 -*-

from odoo import models


class KcProductionEntry(models.Model):
    _name = 'kc.production.entry'
    _inherit = ['kc.production.entry', 'kc.pin.authorization.mixin']

    def action_confirm(self):
        # Enganche mínimo: si hay una regla activa para (kc.production.entry,
        # 'confirm') cuyo dominio aplica, se exige el PIN antes de confirmar.
        action = self._kc_pin_guard('confirm', 'action_confirm')
        if action:
            return action
        return super().action_confirm()

    def action_validate(self):
        # Enganche mínimo: si hay una regla activa para (kc.production.entry,
        # 'validate') cuyo dominio aplica, se exige el PIN antes de validar
        # (la validación impacta inventario).
        action = self._kc_pin_guard('validate', 'action_validate')
        if action:
            return action
        return super().action_validate()

    def action_open_reversal_wizard(self):
        # La reversión genera un movimiento inverso de inventario: se exige el
        # PIN (operación 'reverse') antes de abrir el asistente de motivo.
        action = self._kc_pin_guard('reverse', 'action_open_reversal_wizard')
        if action:
            return action
        return super().action_open_reversal_wizard()
