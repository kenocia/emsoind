# -*- coding: utf-8 -*-
from odoo import fields, models, _


class KcProductionConsumptionReversalWizard(models.TransientModel):
    """Wizard de confirmación para revertir un Consumo de Materia Prima."""
    _name = 'kc.production.consumption.reversal.wizard'
    _description = 'Asistente de Reversión de Consumo de Materia Prima'

    consumption_id = fields.Many2one(
        comodel_name='kc.production.consumption',
        string='Consumo de Materia Prima',
        required=True,
        ondelete='cascade',
    )
    reason = fields.Text(
        string='Motivo de la Reversión',
        required=True,
    )

    def action_confirm_reversal(self):
        """Crea el CMP de reversión y abre el documento generado."""
        self.ensure_one()
        reversal = self.consumption_id.create_reversal(self.reason)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reversión de Consumo'),
            'res_model': 'kc.production.consumption',
            'view_mode': 'form',
            'res_id': reversal.id,
            'target': 'current',
        }
