# -*- coding: utf-8 -*-
from odoo import fields, models


class StockLot(models.Model):
    """Extensión del lote para trazar su origen (OV y/o Registro de Producción)."""
    _inherit = 'stock.lot'

    kc_sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Orden de Venta Origen',
        help="Orden de Venta desde la que se originó este lote (vía RP).",
    )
    kc_entry_id = fields.Many2one(
        comodel_name='kc.production.entry',
        string='Registro de Producción Origen',
        help="Registro de Producción que generó este lote.",
    )
