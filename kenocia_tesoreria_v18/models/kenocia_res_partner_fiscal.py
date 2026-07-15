# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    kenocia_es_proveedor_sar = fields.Boolean(
        string='Proveedor SAR',
        compute='_compute_kenocia_es_proveedor_sar',
        help=(
            'Contacto usado como proveedor en compras con respaldo fiscal '
            'Honduras (RTN y/o facturas en diario FA/Boleta).'
        ),
    )

    @api.depends('supplier_rank', 'vat', 'country_id', 'is_company')
    def _compute_kenocia_es_proveedor_sar(self):
        for partner in self:
            is_supplier = partner.supplier_rank > 0
            is_hn = partner.country_id and partner.country_id.code == 'HN'
            has_rtn = bool(partner.vat)
            partner.kenocia_es_proveedor_sar = (
                is_supplier and is_hn and has_rtn
            ) or (
                is_supplier
                and is_hn
                and not partner.is_company
            )

    def _kenocia_get_fiscal_vendor_label(self):
        """Etiqueta legible del proveedor para liquidación caja chica."""
        self.ensure_one()
        parts = [self.display_name]
        if self.vat:
            parts.append(_('RTN: %s') % self.vat)
        if self.country_id:
            parts.append(self.country_id.name)
        return ' · '.join(parts)
