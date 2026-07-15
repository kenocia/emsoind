# -*- coding: utf-8 -*-
from odoo import fields, models, _


class KcProductionEntryReversalWizard(models.TransientModel):
    """Wizard de confirmación para revertir un Registro de Producción."""
    _name = 'kc.production.entry.reversal.wizard'
    _description = 'Asistente de Reversión de Registro de Producción'

    entry_id = fields.Many2one(
        comodel_name='kc.production.entry',
        string='Registro de Producción',
        required=True,
        ondelete='cascade',
    )
    reason = fields.Text(
        string='Motivo de la Reversión',
        required=True,
    )

    def action_confirm_reversal(self):
        """Crea el RP de reversión y abre el documento generado."""
        self.ensure_one()
        reversal = self.entry_id.create_reversal(self.reason)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reversión de Producción'),
            'res_model': 'kc.production.entry',
            'view_mode': 'form',
            'res_id': reversal.id,
            'target': 'current',
        }
