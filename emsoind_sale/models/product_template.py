# -*- coding: utf-8 -*-

from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _emsoind_force_uppercase_vals(self, vals):
        """Normaliza a mayúsculas los campos de identificación del producto."""
        if not vals:
            return vals
        vals = dict(vals)
        if vals.get('name'):
            vals['name'] = vals['name'].strip().upper()
        if vals.get('default_code'):
            vals['default_code'] = vals['default_code'].strip().upper()
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._emsoind_force_uppercase_vals(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        vals = self._emsoind_force_uppercase_vals(vals)
        return super().write(vals)

    @api.onchange('name')
    def _onchange_emsoind_name_uppercase(self):
        if self.name:
            self.name = self.name.strip().upper()

    @api.onchange('default_code')
    def _onchange_emsoind_default_code_uppercase(self):
        if self.default_code:
            self.default_code = self.default_code.strip().upper()
