# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    kc_simple_production = fields.Boolean(
        string='Producción simple (sin atributos técnicos)',
        default=False,
        help='Permite planificar y producir este PT desde la Orden de Venta '
             'sin ficha técnica ni clave. Es excluyente del modo '
             '"Producto + especificaciones y lote". No usa abastecimiento.',
    )

    @api.constrains(
        'kc_simple_production',
        'kc_invoice_detail_mode',
        'technical_attribute_line_ids',
    )
    def _check_kc_simple_production_exclusive(self):
        for tmpl in self:
            if not tmpl.kc_simple_production:
                continue
            if getattr(tmpl, 'kc_invoice_detail_mode', False) == 'technical':
                raise ValidationError(_(
                    'El producto "%(product)s" no puede tener a la vez '
                    '"Producción simple" y el detalle '
                    '"Producto + especificaciones y lote". '
                    'Elija uno u otro.',
                    product=tmpl.display_name,
                ))
            if getattr(tmpl, 'technical_attribute_line_ids', False):
                raise ValidationError(_(
                    'El producto "%(product)s" tiene atributos técnicos en '
                    'ficha. Quite los atributos o desactive '
                    '"Producción simple".',
                    product=tmpl.display_name,
                ))

    @api.onchange('kc_simple_production')
    def _onchange_kc_simple_production(self):
        if self.kc_simple_production:
            self.kc_invoice_detail_mode = 'product_only'
            if self.tracking != 'lot':
                self.tracking = 'lot'

    @api.onchange('kc_invoice_detail_mode')
    def _onchange_kc_invoice_detail_mode_vs_simple(self):
        if self.kc_invoice_detail_mode == 'technical':
            self.kc_simple_production = False

    def write(self, vals):
        res = super().write(vals)
        if vals.get('kc_simple_production'):
            to_fix = self.filtered(
                lambda t: t.kc_simple_production and t.tracking != 'lot'
            )
            if to_fix:
                super(ProductTemplate, to_fix).write({'tracking': 'lot'})
        return res
