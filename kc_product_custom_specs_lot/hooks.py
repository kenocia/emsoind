# -*- coding: utf-8 -*-


def post_init_hook(env):
    templates = env['product.template'].search([
        '|',
        ('technical_attribute_line_ids', '!=', False),
        ('kc_invoice_detail_mode', '=', 'technical'),
    ])
    templates._kc_apply_technical_product_defaults()
