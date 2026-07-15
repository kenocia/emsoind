# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    emsoind_section_category_id = fields.Many2one(
        comodel_name='product.category',
        string='Categoría de sección EMSOIND',
        copy=False,
        ondelete='set null',
        help='Solo en líneas de sección creadas automáticamente por categoría de producto.',
    )

    @api.model
    def _emsoind_auto_section_enabled(self):
        return self.env['res.config.settings'].emsoind_is_auto_section_by_category_enabled()

    def _emsoind_is_auto_section_product_line(self):
        self.ensure_one()
        return (
            bool(self.product_id)
            and not self.display_type
            and not self.is_downpayment
            and self.product_id.type != 'combo'
        )

    def _emsoind_apply_category_section(self):
        if not self._emsoind_auto_section_enabled():
            return
        if self.env.context.get('emsoind_skip_auto_section'):
            return
        for line in self:
            if not line._emsoind_is_auto_section_product_line():
                continue
            if line.order_id.state not in ('draft', 'sent'):
                continue
            line.order_id._emsoind_place_line_in_category_section(line)
        orders = self.mapped('order_id')
        orders._emsoind_cleanup_empty_auto_sections()
        orders._emsoind_normalize_line_sequences()

    def _emsoind_get_production_line_weight(self):
        """Peso de línea = cantidad pedida × peso unitario del producto."""
        self.ensure_one()
        if self.display_type or not self.product_id:
            return 0.0
        return self.product_uom_qty * (self.product_id.weight or 0.0)

    def _emsoind_get_production_line_description(self):
        """Descripción en una sola línea: código, producto y dimensiones."""
        self.ensure_one()
        if self.display_type:
            return (self.name or '').strip()
        label = (self.name or '').strip()
        if not label and self.product_id:
            label = self.product_id.display_name
        if 'technical_description' in self._fields:
            tech = (self.technical_description or '').strip().replace('\n', ' ')
            if tech and tech not in label:
                label = '%s %s' % (label, tech) if label else tech
        return label

    @api.model_create_multi
    def create(self, vals_list):
        Order = self.env['sale.order']
        for vals in vals_list:
            order_id = vals.get('order_id')
            if not order_id or vals.get('display_type'):
                continue
            order = Order.browse(order_id)
            if not order.exists():
                continue
            existing_seqs = order.order_line.mapped('sequence')
            if not existing_seqs:
                continue
            max_seq = max(existing_seqs)
            # Forzar al final si no hay sequence o queda al inicio del detalle.
            current = vals.get('sequence', 10)
            if current is None or current <= min(existing_seqs):
                vals['sequence'] = max_seq + 10
        lines = super().create(vals_list)
        lines._emsoind_apply_category_section()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if 'product_id' in vals or 'display_type' in vals:
            self._emsoind_apply_category_section()
        return res

    def unlink(self):
        orders = self.mapped('order_id')
        res = super().unlink()
        if self._emsoind_auto_section_enabled():
            orders._emsoind_cleanup_empty_auto_sections()
            orders._emsoind_normalize_line_sequences()
        return res
