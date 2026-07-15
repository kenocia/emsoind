# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote',
        compute='_compute_sale_technical_info',
        store=True,
        readonly=True,
    )
    technical_description = fields.Text(
        string='Descripción técnica',
        compute='_compute_sale_technical_info',
        store=True,
        readonly=True,
    )
    technical_key = fields.Char(
        string='Clave técnica',
        compute='_compute_sale_technical_info',
        store=True,
        readonly=True,
    )
    kc_invoice_detail_mode = fields.Selection(
        related='product_id.product_tmpl_id.kc_invoice_detail_mode',
        string='Modo detalle factura',
        readonly=True,
    )
    kc_show_technical_on_invoice = fields.Boolean(
        string='Mostrar detalle técnico',
        compute='_compute_kc_show_technical_on_invoice',
        store=True,
        readonly=True,
    )

    @api.depends(
        'sale_line_ids',
        'sale_line_ids.lot_id',
        'sale_line_ids.technical_description',
        'sale_line_ids.technical_key',
        'sale_line_ids.product_id',
        'product_id',
        'product_id.product_tmpl_id.kc_invoice_detail_mode',
    )
    def _compute_sale_technical_info(self):
        for line in self:
            lot = False
            description = False
            technical_key = False
            sale_line = line.sale_line_ids[:1]
            if sale_line:
                lot = sale_line.lot_id
                description = sale_line.technical_description
                technical_key = sale_line.technical_key
            line.lot_id = lot
            line.technical_description = description
            line.technical_key = technical_key

    @api.depends(
        'product_id',
        'quantity',
        'price_subtotal',
        'lot_id',
        'lot_id.standard_price',
        'technical_key',
        'move_id.company_id',
    )
    def _compute_kc_cost_margin(self):
        for line in self:
            if not line.product_id or line.display_type:
                line.kc_unit_cost = 0.0
                line.kc_margin = 0.0
                line.kc_margin_percent = 0.0
                continue
            cost = line.env['stock.lot']._kc_resolve_unit_cost(
                line.product_id,
                technical_key=line.technical_key,
                lot=line.lot_id,
                company=line.company_id,
            )
            unit_cost = line.product_id.uom_id._compute_price(cost, line.product_uom_id)
            qty = line.quantity or 0.0
            line.kc_unit_cost = unit_cost
            line.kc_margin = line.price_subtotal - (unit_cost * qty)
            line.kc_margin_percent = (
                line.price_subtotal and line.kc_margin / line.price_subtotal
            )

    kc_unit_cost = fields.Float(
        string='Costo unitario',
        compute='_compute_kc_cost_margin',
        digits='Product Price',
        groups='base.group_user',
    )
    kc_margin = fields.Monetary(
        string='Margen',
        compute='_compute_kc_cost_margin',
        currency_field='currency_id',
        groups='base.group_user',
    )
    kc_margin_percent = fields.Float(
        string='Margen (%)',
        compute='_compute_kc_cost_margin',
        groups='base.group_user',
    )

    @api.depends(
        'kc_invoice_detail_mode',
        'technical_description',
        'lot_id',
        'display_type',
    )
    def _compute_kc_show_technical_on_invoice(self):
        for line in self:
            show = (
                line.kc_invoice_detail_mode == 'technical'
                and line.display_type == 'product'
                and (line.technical_description or line.lot_id)
            )
            line.kc_show_technical_on_invoice = show
