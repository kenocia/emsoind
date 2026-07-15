# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # Mantener subtotal alineado al campo monetario estándar de Odoo 19.
    price_subtotal = fields.Monetary(compute='_compute_totals', string='Subtotal', store=True, currency_field='currency_id')
    
    base_imponible = fields.Float(string='Base Imponible', required=False)
    porcentaje_retencion = fields.Float(string='% de Retención', required=False)

    kc_discount_amount = fields.Monetary(
        string='Descuento (línea)',
        currency_field='currency_id',
        compute='_compute_kc_discount_amount',
        store=True,
        readonly=True,
        help='Monto descontado en la línea (% sobre precio o producto Desc). Coherente con amount_discount en la '
        'factura; price_subtotal y apuntes ya reflejan el importe neto.',
    )

    @api.depends(
        'display_type',
        'quantity',
        'price_unit',
        'discount',
        'price_subtotal',
        'product_id',
        'product_id.product_tmpl_id.default_code',
        'move_id',
        'move_id.move_type',
        'move_id.currency_id',
    )
    def _compute_kc_discount_amount(self):
        for line in self:
            line.kc_discount_amount = 0.0
            # Odoo 18: líneas de producto tienen display_type='product' (no False).
            if line.display_type not in (False, 'product') and not (not line.display_type and line.product_id):
                continue
            move = line.move_id
            if not move or not move.is_invoice(include_receipts=True):
                continue
            cur = move.currency_id
            if line.discount:
                gross = line.quantity * line.price_unit
                disc = abs(gross * (line.discount / 100.0))
                line.kc_discount_amount = cur.round(disc) if cur else round(disc, 4)
            elif line.product_id and line.product_id.product_tmpl_id.default_code == 'Desc':
                disc = abs(line.price_subtotal)
                line.kc_discount_amount = cur.round(disc) if cur else round(disc, 4)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            # Obtener el impuesto de retención del producto
            tax_retention = self.product_id.tax_retention
            invoice_retention = self.move_id.invoice_retention
            if tax_retention:
                self.base_imponible = invoice_retention.amount_untaxed
                self.porcentaje_retencion = abs(tax_retention.amount)

                self.price_unit = self.base_imponible * self.porcentaje_retencion / 100

    @api.onchange('product_id')
    def _onchange_product_retencion_isr_hn(self):
        """Aplica retención ISR en líneas de compra según reglas SAR."""
        if not self.move_id or self.move_id.move_type != 'in_invoice':
            return
        if not self.product_id or not self.move_id.partner_id:
            return

        partner = self.move_id.partner_id
        product = self.product_id

        if partner.country_id and partner.country_id.code != 'HN':
            return
        if not partner.vat:
            return
        if partner.constancia_vigente:
            return
        if not product.aplica_retencion_isr:
            return
        if not product.impuesto_retencion_isr_id:
            return

        impuesto_ret = product.impuesto_retencion_isr_id
        if impuesto_ret not in self.tax_ids:
            self.tax_ids = self.tax_ids | impuesto_ret

