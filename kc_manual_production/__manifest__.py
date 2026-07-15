# -*- coding: utf-8 -*-
{
    'name': 'Planta KC',
    'version': '18.0.1.28.3',
    'category': 'Inventory/Inventory',
    'summary': 'Control manual de producción y consumo de materia prima sin MRP, con trazabilidad por lote',
    'description': """
Módulo transitorio de control de producción manual para empresas que aún no
implementan el módulo de Manufactura (MRP) de Odoo.

Roles:
- Planificador: planifica y genera RP en borrador (no confirma ni valida).
- Operador de Producción: planifica, genera RP y confirma.
- Operador de Bodega: valida recepción PT y CMP.
- Administrador de Producción: acceso total.
    """,
    'author': 'Kenocia (Kenosis Company)',
    'website': 'https://kenocia.com',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'stock_account',
        'sale',
        'sale_stock',
        'account',
        'analytic',
        'sales_team',
        'resource',
        'web_gantt',
        'kc_product_custom_specs_lot',
    ],
    'data': [
        'security/kc_production_security.xml',
        'security/kc_production_line_security.xml',
        'security/kc_production_plan_security.xml',
        'security/ir.model.access.csv',
        'security/kc_production_multicompany_rules.xml',
        'data/sequences.xml',
        'data/kc_production_line_data.xml',
        'data/stock_route_data.xml',
        'views/kc_production_line_views.xml',
        'views/product_template_views.xml',
        'views/kc_work_center_views.xml',
        'views/kc_production_entry_views.xml',
        'views/kc_production_consumption_views.xml',
        'views/kc_production_plan_views.xml',
        'views/kc_production_backlog_views.xml',
        'views/sale_order_views.xml',
        'views/stock_lot_views.xml',
        'views/stock_picking_type_views.xml',
        'views/kc_production_dashboard_views.xml',
        'wizard/kc_production_entry_reversal_wizard_views.xml',
        'wizard/kc_production_consumption_reversal_wizard_views.xml',
        'wizard/kc_replenishment_rp_wizard_views.xml',
        'wizard/kc_production_plan_print_wizard_views.xml',
        'wizard/kc_production_backlog_mass_plan_wizard_views.xml',
        'report/kc_production_entry_report.xml',
        'report/kc_production_consumption_report.xml',
        'report/kc_production_plan_reports.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'kc_manual_production/static/src/dashboard/production_dashboard.js',
            'kc_manual_production/static/src/dashboard/production_dashboard.xml',
            'kc_manual_production/static/src/dashboard/production_dashboard.scss',
            'kc_manual_production/static/src/manual/kc_manual.js',
            'kc_manual_production/static/src/manual/kc_manual.xml',
            'kc_manual_production/static/src/manual/kc_manual.scss',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'application': True,
    'installable': True,
    'auto_install': False,
}
