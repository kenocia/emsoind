# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class SarPrintReissueWizard(models.TransientModel):
    _name = 'kc_fiscal_hn.print.reissue.wizard'
    _description = 'Autorizar reimpresión SAR como Original'

    move_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
        readonly=True,
    )
    reason = fields.Text(string='Motivo', required=True)

    def action_authorize(self):
        self.ensure_one()
        move = self.move_id
        if not move:
            raise UserError(_('Debe seleccionar una factura.'))
        if move.sar_print_reissue_authorized:
            raise UserError(_(
                'Ya existe una reautorización pendiente para este documento.',
            ))
        move._sar_print_authorize_reissue(self.reason)
        return {'type': 'ir.actions.act_window_close'}
