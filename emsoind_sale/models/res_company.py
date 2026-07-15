# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    generic_vendor_id = fields.Many2one(
        domain=lambda self: self.env['res.partner'].EMSOIND_SUPPLIER_DOMAIN,
    )

    @api.constrains('generic_vendor_id')
    def _check_generic_vendor_is_supplier(self):
        for company in self:
            partner = company.generic_vendor_id
            if not partner:
                continue
            if partner.supplier_rank or partner.emsoind_use_in_purchases:
                continue
            raise ValidationError(
                'El proveedor genérico debe ser un proveedor registrado '
                'en el sistema (rank de proveedor o etiqueta de compras EMSOIND).'
            )
