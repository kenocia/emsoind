# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResPartnerCategory(models.Model):
    _inherit = 'res.partner.category'

    use_in_sales = fields.Boolean(
        string='Visible en ventas',
        help='Los contactos con esta etiqueta aparecen en cotizaciones/pedidos '
             'y en el menú Ventas → Clientes.',
    )
    use_in_purchases = fields.Boolean(
        string='Visible en compras',
        help='Los contactos con esta etiqueta aparecen en órdenes de compra '
             'y en el menú Compras → Proveedores.',
    )
    require_sales_fields = fields.Boolean(
        string='Exigir datos de venta',
        help='Al guardar, valida nombre, RTN, país, dirección, teléfono, '
             'vendedor y término de pago en el contacto comercial.',
    )
    require_purchase_fields = fields.Boolean(
        string='Exigir datos de compra',
        help='Reservado para validaciones futuras en contactos de compras.',
    )

    @api.model
    def _emsoind_run_post_upgrade(self):
        from odoo.addons.emsoind_sale.hooks import (
            _emsoind_cleanup_supplier_customer_rank,
            _emsoind_configure_categories,
        )
        _emsoind_configure_categories(self.env)
        _emsoind_cleanup_supplier_customer_rank(self.env)
