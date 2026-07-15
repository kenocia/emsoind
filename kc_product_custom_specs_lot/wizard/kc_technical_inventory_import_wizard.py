# -*- coding: utf-8 -*-

import base64

from odoo import _, fields, models
from odoo.exceptions import UserError


class KcTechnicalInventoryImportWizard(models.TransientModel):
    _name = 'kc.technical.inventory.import.wizard'
    _description = 'Importar inventario inicial por configuración técnica'

    file_data = fields.Binary(string='Archivo Excel/CSV', required=True)
    file_name = fields.Char(string='Nombre del archivo')
    location_id = fields.Many2one(
        'stock.location',
        string='Ubicación destino',
        domain="[('usage', '=', 'internal')]",
        help='Ubicación donde se cargará el inventario (ej. ESI/Bodega PT).',
    )
    inventory_date = fields.Date(
        string='Fecha de inventario',
        default='2026-06-30',
        required=True,
        help='Fecha de corte del inventario inicial (afecta in_date del quant).',
    )
    merge_existing_lot = fields.Boolean(
        string='Sumar cantidades si el lote ya existe',
        default=True,
        help='Si ya hay stock del mismo lote en la ubicación, suma la cantidad '
             'del archivo en lugar de rechazar la fila.',
    )
    result_message = fields.Text(string='Resultado', readonly=True)

    def action_import(self):
        self.ensure_one()
        if not self.file_data:
            raise UserError(_('Seleccione un archivo Excel o CSV para importar.'))
        result = self.env['stock.lot'].import_initial_inventory(
            base64.b64decode(self.file_data),
            file_name=self.file_name,
            location=self.location_id,
            inventory_date=self.inventory_date,
            merge_existing_lot=self.merge_existing_lot,
        )
        message = result['message']
        if result.get('location'):
            message += '\n' + _('Ubicación: %s') % result['location']
        if result.get('errors'):
            message += '\n\n' + '\n'.join(result['errors'])
        self.result_message = message
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
