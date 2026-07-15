# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, fields, models
from odoo.exceptions import UserError


class KenociaVoidWizard(models.TransientModel):
    _name = 'kenocia.void.wizard'
    _description = 'Wizard — Anular Cheque de Tesorería'

    payment_id = fields.Many2one(
        comodel_name='account.payment',
        string='Pago',
        required=True,
        readonly=True,
    )
    payment_name = fields.Char(
        related='payment_id.kenocia_sequence_name',
        string='Número de cheque',
    )
    void_reason = fields.Text(
        string='Motivo de anulación',
        required=True,
    )

    def action_confirm_void(self):
        self.ensure_one()
        if not self.void_reason or not self.void_reason.strip():
            raise UserError(_('Debe indicar el motivo de anulación.'))
        self.payment_id._action_void_cheque_confirm(self.void_reason)
        return {'type': 'ir.actions.act_window_close'}
