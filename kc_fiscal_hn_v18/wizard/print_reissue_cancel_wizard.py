# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class SarPrintReissueCancelWizard(models.TransientModel):
    _name = 'kc_fiscal_hn.print.reissue.cancel.wizard'
    _description = 'Cancelar reautorización de impresión SAR'

    move_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
        readonly=True,
    )
    reason = fields.Text(string='Motivo de cancelación', required=True)

    def action_cancel_authorization(self):
        self.ensure_one()
        move = self.move_id
        if not move:
            raise UserError(_('Debe seleccionar una factura.'))
        if not move.sar_print_reissue_authorized:
            raise UserError(_(
                'No hay una reautorización pendiente que cancelar.',
            ))
        move._sar_print_cancel_reissue(self.reason)
        return {'type': 'ir.actions.act_window_close'}
