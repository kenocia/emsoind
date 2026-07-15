# -*- coding: utf-8 -*-


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    templates = env['product.template'].search([
        '|',
        ('technical_attribute_line_ids', '!=', False),
        ('kc_invoice_detail_mode', '=', 'technical'),
    ])
    templates._kc_apply_technical_product_defaults()
