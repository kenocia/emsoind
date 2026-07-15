# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        self._kc_validate_outgoing_lot_specs()
        return super().button_validate()

    def _kc_validate_outgoing_lot_specs(self):
        for picking in self.filtered(lambda p: p.picking_type_code == 'outgoing'):
            for move in picking.move_ids:
                sale_line = move.sale_line_id
                if not sale_line or not sale_line._requires_technical_specs():
                    continue
                if not sale_line.technical_key:
                    continue
                move_lines = move.move_line_ids.filtered(lambda ml: ml.quantity > 0)
                if not move_lines:
                    continue
                for ml in move_lines:
                    if not ml.lot_id:
                        raise UserError(
                            _('Indique el lote en la entrega para %(product)s '
                              '(especificación: %(spec)s).')
                            % {
                                'product': move.product_id.display_name,
                                'spec': sale_line.technical_description or sale_line.technical_key,
                            }
                        )
                    if ml.lot_id.technical_key and ml.lot_id.technical_key != sale_line.technical_key:
                        raise UserError(
                            _('El lote %(lot)s no coincide con la especificación de la venta '
                              '(%(expected)s).')
                            % {
                                'lot': ml.lot_id.name,
                                'expected': sale_line.technical_description or sale_line.technical_key,
                            }
                        )
