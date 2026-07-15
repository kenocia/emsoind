# -*- coding: utf-8 -*-
from odoo import api, fields, models


class KcSaleOrderProductionProgress(models.Model):
    """Filas virtuales de avance de producción por producto (seguimiento vendedor)."""
    _name = 'kc.sale.order.production.progress'
    _description = 'Avance de Producción por Producto (OV)'
    _order = 'sequence, id'

    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Orden de Venta',
        ondelete='cascade',
    )
    sale_order_line_id = fields.Many2one(
        comodel_name='sale.order.line',
        string='Línea de OV',
    )
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Producto',
    )
    technical_description = fields.Text(string='Descripción técnica')
    qty_ordered = fields.Float(
        string='Cantidad OV',
        digits='Product Unit of Measure',
    )
    qty_planned = fields.Float(
        string='Planificado',
        digits='Product Unit of Measure',
    )
    qty_confirmed = fields.Float(
        string='Confirmado (prod.)',
        digits='Product Unit of Measure',
    )
    qty_validated = fields.Float(
        string='Validado (stock)',
        digits='Product Unit of Measure',
    )
    qty_pending = fields.Float(
        string='Pendiente',
        digits='Product Unit of Measure',
    )
    status = fields.Selection(
        selection=[
            ('none', 'Sin producir'),
            ('planned', 'Planificado'),
            ('confirmed', 'En producción'),
            ('parcial', 'Parcial'),
            ('done', 'Completo'),
        ],
        string='Estado',
    )
