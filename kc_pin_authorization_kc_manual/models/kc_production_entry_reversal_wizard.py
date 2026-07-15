# -*- coding: utf-8 -*-

from odoo import models


class KcProductionEntryReversalWizard(models.TransientModel):
    _name = 'kc.production.entry.reversal.wizard'
    _inherit = ['kc.production.entry.reversal.wizard', 'kc.pin.authorization.mixin']

    def action_confirm_reversal(self):
        # La reversión impacta inventario: si hay una regla activa para
        # (kc.production.entry.reversal.wizard, 'validate') cuyo dominio aplica,
        # se exige el PIN antes de confirmar la reversión del Registro de
        # Producción. Se usa 'validate' porque el botón "Confirmar Reversión" es
        # el punto en que se ejecuta el movimiento inverso.
        action = self._kc_pin_guard('validate', 'action_confirm_reversal')
        if action:
            return action
        return super().action_confirm_reversal()
