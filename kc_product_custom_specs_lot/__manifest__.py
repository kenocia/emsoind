# -*- coding: utf-8 -*-
{
    'name': 'KC Producto: Especificaciones Técnicas por Lote',
    'summary': 'Especificaciones técnicas dinámicas en ventas e inventario por lote',
    'description': """
        Productos genéricos con especificaciones técnicas en líneas de venta.
        El stock se diferencia por lote según la especificación técnica.
        Modal de configuración, autorización PIN y trazabilidad en inventario.
    """,
    'version': '18.0.3.19.3',
    'category': 'Sales/Inventory',
    'author': 'KENOCIA',
    'website': 'https://kenocia.com/',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'stock',
        'stock_account',
        'account',
        'uom',
        'sale_stock',
        'hr',
        'kc_pin_authorization',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/technical_attribute_views.xml',
        'views/product_template_views.xml',
        'wizard/kc_technical_configuration_cost_wizard_views.xml',
        'wizard/kc_technical_inventory_import_wizard_views.xml',
        'views/product_technical_configuration_views.xml',
        'views/product_pricelist_item_views.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
        'views/stock_lot_views.xml',
        'views/stock_inventory_views.xml',
        'views/stock_quant_technical_views.xml',
        'views/kc_technical_orderpoint_views.xml',
        'views/account_move_views.xml',
        'wizard/sale_line_specs_wizard_views.xml',
        'wizard/compatible_lot_wizard_views.xml',
        'wizard/copy_technical_specs_wizard_views.xml',
        'reports/sale_report_templates.xml',
        'reports/sale_portal_templates.xml',
        'reports/stock_report_templates.xml',
        'reports/account_report_templates.xml',
        'reports/inventory_report_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'kc_product_custom_specs_lot/static/src/js/sale_specs_product_field.js',
        ],
        'web.assets_frontend': [
            'kc_product_custom_specs_lot/static/src/scss/sale_portal.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
    'images': ['static/description/icon.png'],
}
