# -*- coding: utf-8 -*-
{
    'name': 'EMSOIND Ventas — Contactos comerciales',
    'summary': 'Etiquetas de contacto con control ventas/compras y campos obligatorios',
    'description': """
        Extensión EMSOIND para contactos comerciales:

        * Etiquetas con flags: visible en ventas, visible en compras, campos obligatorios
        * Filtrado de clientes/proveedores en OV, OC, solicitudes de compra y menús
        * Auto-etiqueta al crear desde ventas o compras
        * Validación de datos mínimos del cliente comercial
        * Secciones automáticas por categoría de producto en cotizaciones/pedidos
        * Reporte operativo Orden de Producción (solo OV confirmadas)
        * Menú Facturadas: una fila por factura publicada, abre la OV al consultar
        * Validación comercial antes de confirmar (vendedor valida, gerente confirma + PIN)
        * Nuevas líneas de producto al final del detalle
    """,
    'version': '18.0.1.4.5',
    'category': 'Sales',
    'author': 'Kenocia (Kenosis Company)',
    'website': 'https://kenocia.com/',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'sale_stock',
        'sale_project',
        'purchase',
        'account',
        'mail',
        'kc_fiscal_hn_v18',
        'kc_purchase_request_v18',
        'kc_pin_authorization_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/partner_category_data.xml',
        'data/mail_activity_type_data.xml',
        'data/pin_authorization_rule_data.xml',
        'views/res_partner_category_views.xml',
        'views/res_partner_views.xml',
        'views/partner_action_views.xml',
        'views/sale_order_views.xml',
        'views/emsoind_sale_order_invoice_views.xml',
        'report/sale_production_order_report.xml',
        'views/res_config_settings_views.xml',
        'views/purchase_order_views.xml',
        'views/kc_purchase_request_views.xml',
        'data/post_upgrade.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'assets': {
        'web.assets_backend': [
            'emsoind_sale/static/src/scss/sale_order_line_wrap.scss',
        ],
    },
}
