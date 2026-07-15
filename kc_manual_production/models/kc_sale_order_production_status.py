# -*- coding: utf-8 -*-
from odoo import fields, models


class KcSaleOrderProductionStatus(models.Model):
    """Filas de resumen (no almacenadas) del estado de producción por línea en una OV."""
    _name = 'kc.sale.order.production.status'
    _description = 'Estado de Producción por Línea (OV)'
    _order = 'sequence, id'

    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Orden de Venta',
        ondelete='cascade',
    )
    production_line_id = fields.Many2one(
        comodel_name='kc.production.line',
        string='Línea de Producción',
    )
    sequence = fields.Integer(default=10)
    product_summary = fields.Char(string='Productos')
    entry_id = fields.Many2one(
        comodel_name='kc.production.entry',
        string='Registro de Producción',
    )
    entry_state = fields.Selection(
        related='entry_id.state',
        string='Estado RP',
    )
    status = fields.Selection(
        selection=[
            ('none', 'Sin productos'),
            ('pending', 'Pendiente'),
            ('draft', 'Borrador'),
            ('confirmed', 'Confirmado'),
            ('parcial', 'Parcial'),
            ('done', 'Validado / Completo'),
            ('cancel', 'Cancelado'),
        ],
        string='Estado',
    )
    status_label = fields.Char(
        string='Estado (texto)',
        compute='_compute_status_label',
    )

    def _compute_status_label(self):
        labels = dict(self._fields['status'].selection)
        for rec in self:
            rec.status_label = labels.get(rec.status, '')
