# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'
    _order = (
        'applied_on, min_quantity desc, categ_id desc, '
        'technical_key desc, technical_configuration_id desc, id desc'
    )

    technical_configuration_id = fields.Many2one(
        'product.technical.configuration',
        string='Configuración técnica (matriz)',
        ondelete='restrict',
        index=True,
        domain="[('product_tmpl_id', '=', product_tmpl_id)]",
    )
    technical_key = fields.Char(
        string='Clave técnica (matriz)',
        index=True,
        help='Matriz completa de especificaciones. Se sincroniza al elegir una configuración técnica.',
    )

    @api.onchange('technical_configuration_id')
    def _onchange_technical_configuration_id(self):
        for item in self:
            config = item.technical_configuration_id
            if not config:
                item.technical_key = False
                continue
            item.technical_key = config.technical_key
            if not item.product_tmpl_id:
                item.applied_on = '1_product'
                item.product_tmpl_id = config.product_tmpl_id

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        Configuration = self.env['product.technical.configuration']
        for vals in vals_list:
            vals = dict(vals)
            if vals.get('technical_configuration_id') and not vals.get('technical_key'):
                config = Configuration.browse(vals['technical_configuration_id'])
                vals['technical_key'] = config.technical_key
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        if vals.get('technical_configuration_id') and 'technical_key' not in vals:
            config = self.env['product.technical.configuration'].browse(
                vals['technical_configuration_id']
            )
            vals = dict(vals, technical_key=config.technical_key)
        return super().write(vals)

    @api.onchange('product_tmpl_id', 'product_id')
    def _onchange_product_technical_configuration(self):
        for item in self:
            if not item.technical_configuration_id:
                continue
            tmpl = item.product_tmpl_id or (
                item.product_id.product_tmpl_id if item.product_id else False
            )
            if tmpl and item.technical_configuration_id.product_tmpl_id != tmpl:
                item.technical_configuration_id = False
                item.technical_key = False

    @api.constrains(
        'technical_configuration_id',
        'technical_key',
        'product_tmpl_id',
        'product_id',
    )
    def _check_technical_matrix_pricelist(self):
        for item in self:
            if not item.technical_configuration_id and not item.technical_key:
                continue
            tmpl = item.product_tmpl_id or (
                item.product_id.product_tmpl_id if item.product_id else False
            )
            if not tmpl:
                raise ValidationError(
                    _('Las reglas por matriz técnica requieren un producto definido.')
                )
            config = item.technical_configuration_id
            if config:
                if config.product_tmpl_id != tmpl:
                    raise ValidationError(
                        _('La configuración técnica debe pertenecer al mismo producto de la regla.')
                    )
                if item.technical_key and item.technical_key != config.technical_key:
                    raise ValidationError(
                        _('La clave técnica no coincide con la configuración seleccionada.')
                    )

    def _kc_item_technical_key(self):
        self.ensure_one()
        if self.technical_key:
            return self.technical_key
        if self.technical_configuration_id:
            return self.technical_configuration_id.technical_key
        return False

    def _is_applicable_for(self, product, qty_in_product_uom):
        res = super()._is_applicable_for(product, qty_in_product_uom)
        if not res:
            return res

        item_key = self._kc_item_technical_key()
        if not item_key:
            return res

        line_technical_key = self.env.context.get('kc_technical_key')
        return bool(line_technical_key) and line_technical_key == item_key
