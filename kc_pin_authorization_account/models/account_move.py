# -*- coding: utf-8 -*-

from odoo import models


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'kc.pin.authorization.mixin']

    def action_post(self):
        # Enganche mínimo: si hay una regla activa para (account.move, 'post')
        # cuyo dominio aplica a estos asientos, se exige el PIN antes de
        # publicar. El alcance se controla desde Ajustes (se recomienda acotar
        # con un dominio, p. ej. move_type = out_invoice).
        action = self._kc_pin_guard('post', 'action_post')
        if action:
            return action
        return super().action_post()
