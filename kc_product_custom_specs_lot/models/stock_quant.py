# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    lot_technical_description = fields.Text(
        related='lot_id.technical_description',
        string='Especificaciones',
        store=True,
        readonly=True,
    )
    lot_technical_key = fields.Char(
        related='lot_id.technical_key',
        string='Clave técnica',
        store=True,
        readonly=True,
    )

    @api.model
    def action_view_quants(self):
        """Vista Ubicaciones / stock por ubicación: lista con especificaciones."""
        action = super().action_view_quants()
        ctx = self.env.context
        if ctx.get('always_show_loc') and not ctx.get('inventory_mode'):
            view = self.env.ref(
                'kc_product_custom_specs_lot.view_stock_quant_tree_technical_locations',
                raise_if_not_found=False,
            )
            if view:
                action['view_id'] = view.id
                action['views'] = [(view.id, 'list')]
        return action

    @api.model
    def action_view_technical_inventory(self, product_ids=None):
        domain = [
            ('location_id.usage', '=', 'internal'),
            ('quantity', '!=', 0),
        ]
        if product_ids:
            domain.append(('product_id', 'in', product_ids))
        return {
            'name': _('Existencias por lote y especificación'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.quant',
            'view_mode': 'list,form',
            'views': [(
                self.env.ref(
                    'kc_product_custom_specs_lot.view_stock_quant_tree_technical_inventory'
                ).id,
                'list',
            )],
            'search_view_id': self.env.ref('stock.quant_search_view').id,
            'domain': domain,
            'context': {
                'search_default_internal_loc': 1,
            },
        }


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def action_kc_view_stock_by_lot_specs(self):
        return self.env['stock.quant'].action_view_technical_inventory(
            product_ids=self.ids,
        )
