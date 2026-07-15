# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    generic_vendor_id = fields.Many2one(
        domain=lambda self: self.env['res.partner'].EMSOIND_SUPPLIER_DOMAIN,
    )
    emsoind_auto_section_by_category = fields.Boolean(
        string='Secciones automáticas por categoría',
        config_parameter='emsoind_sale.auto_section_by_category',
        help='Al agregar un producto en una cotización/pedido, crea o reutiliza '
             'una sección con la ruta completa de su categoría de producto.',
    )

    def set_values(self):
        super().set_values()
        # Odoo elimina el parámetro cuando el booleano es False; persistir 'False'
        # explícitamente para que la lectura en ventas respete el ajuste.
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param(
            'emsoind_sale.auto_section_by_category',
            'True' if self.emsoind_auto_section_by_category else 'False',
        )

    @api.model
    def emsoind_is_auto_section_by_category_enabled(self):
        """Lectura centralizada del ajuste de secciones automáticas."""
        value = self.env['ir.config_parameter'].sudo().get_param(
            'emsoind_sale.auto_section_by_category',
            'True',
        )
        return str(value).lower() in ('true', '1', 'yes')
