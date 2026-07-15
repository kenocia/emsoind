# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class KcCopyTechnicalSpecsWizard(models.TransientModel):
    _name = 'kc.copy.technical.specs.wizard'
    _description = 'Copiar especificaciones técnicas'

    sale_order_id = fields.Many2one('sale.order', required=True)
    target_line_id = fields.Many2one('sale.order.line', required=True)
    source_line_id = fields.Many2one(
        'sale.order.line',
        string='Copiar desde línea',
        domain="[('order_id', '=', sale_order_id), ('id', '!=', target_line_id)]",
    )

    def action_copy(self):
        self.ensure_one()
        if not self.source_line_id:
            raise UserError(_('Seleccione la línea de origen.'))
        if not self.source_line_id.technical_value_ids:
            raise UserError(_('La línea de origen no tiene especificaciones.'))
        self.target_line_id._copy_technical_values_from_line(self.source_line_id)
        return {'type': 'ir.actions.act_window_close'}
