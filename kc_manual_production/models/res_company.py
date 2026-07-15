# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    kc_cmp_mp_category_id = fields.Many2one(
        comodel_name='product.category',
        string='Categoría MP (CMP)',
        help="Productos de esta categoría y sus subcategorías se ofrecen en "
             "líneas de consumo tipo Materia Prima.",
    )
    kc_cmp_supply_category_id = fields.Many2one(
        comodel_name='product.category',
        string='Categoría Insumos (CMP)',
        help="Productos de esta categoría y sus subcategorías se ofrecen en "
             "líneas de consumo tipo Insumo.",
    )

    def _kc_cmp_resolve_mp_category(self):
        """Categoría raíz MP para filtrar productos en líneas de material."""
        self.ensure_one()
        if self.kc_cmp_mp_category_id:
            return self.kc_cmp_mp_category_id
        return self.env['product.category'].search([
            ('name', '=', 'MP'),
            ('parent_id', '=', False),
        ], limit=1)

    def _kc_cmp_resolve_supply_category(self):
        """Categoría raíz INSUMOS para filtrar productos en líneas de insumo."""
        self.ensure_one()
        if self.kc_cmp_supply_category_id:
            return self.kc_cmp_supply_category_id
        return self.env['product.category'].search([
            ('name', '=', 'INSUMOS'),
            ('parent_id', '=', False),
        ], limit=1)
