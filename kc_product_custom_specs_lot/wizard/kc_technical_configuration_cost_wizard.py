# -*- coding: utf-8 -*-

import base64

from odoo import _, fields, models
from odoo.exceptions import UserError


class KcTechnicalConfigurationCostWizard(models.TransientModel):
    _name = 'kc.technical.configuration.cost.wizard'
    _description = 'Importar costos de configuraciones técnicas'

    file_data = fields.Binary(string='Archivo CSV', required=True)
    file_name = fields.Char(string='Nombre del archivo')
    result_message = fields.Text(string='Resultado', readonly=True)

    def action_import(self):
        self.ensure_one()
        if not self.file_data:
            raise UserError(_('Seleccione un archivo CSV para importar.'))
        result = self.env['product.technical.configuration'].import_costs_from_csv(
            base64.b64decode(self.file_data),
        )
        self.result_message = result['message']
        if result.get('errors'):
            self.result_message += '\n\n' + '\n'.join(result['errors'])
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
