# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class KcCompatibleLotWizard(models.TransientModel):
    _name = 'kc.compatible.lot.wizard'
    _description = 'Buscar stock compatible por especificación'

    sale_order_line_id = fields.Many2one(
        'sale.order.line',
        required=True,
        ondelete='cascade',
    )
    line_ids = fields.One2many(
        'kc.compatible.lot.wizard.line',
        'wizard_id',
        string='Lotes compatibles',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        line_id = self.env.context.get('default_sale_order_line_id')
        if line_id:
            sale_line = self.env['sale.order.line'].browse(line_id)
            res['line_ids'] = sale_line._prepare_compatible_lot_wizard_lines()
        return res

    def action_select_lot(self):
        self.ensure_one()
        selected = self.line_ids.filtered('selected')
        if len(selected) != 1:
            raise UserError(_('Seleccione exactamente un lote.'))
        self.sale_order_line_id.lot_id = selected.lot_id
        return {'type': 'ir.actions.act_window_close'}


class KcCompatibleLotWizardLine(models.TransientModel):
    _name = 'kc.compatible.lot.wizard.line'
    _description = 'Línea de lote compatible'

    wizard_id = fields.Many2one('kc.compatible.lot.wizard', ondelete='cascade')
    selected = fields.Boolean(string='Seleccionar')
    lot_id = fields.Many2one('stock.lot', required=True)
    location_id = fields.Many2one('stock.location')
    available_qty = fields.Float(string='Disponible')
    technical_description = fields.Text(string='Especificaciones')
