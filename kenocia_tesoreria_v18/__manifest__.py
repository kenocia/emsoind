# -*- coding: utf-8 -*-
{
    'name': 'Kenocia Tesorería v18',
    'summary': 'Tesorería empresarial con pagos anticipados y caja chica SAR-compliant',
    'description': """
        Módulo de Tesorería Empresarial — Kenocia / Odoo 18
        =====================================================

        * Motor de secuencias bancarias con lock atómico (SELECT FOR UPDATE NOWAIT)
        * Pagos anticipados CXC/CXP con aplicación a facturas vía conciliación nativa
        * Cheques, depósitos, débitos y transferencias con tracking completo
        * Caja Chica integrada: fondos, anticipos a empleados y liquidación SAR
        * Contabilidad 100%% nativa — sin asientos personalizados ni cuentas hardcodeadas
    """,
    'author': 'Kenocia (Kenosis Company)',
    'website': 'https://kenocia.com/',
    'support': 'consultoria@kenocia.com',
    'maintainer': 'Kenocia (Kenosis Company)',
    'license': 'LGPL-3',
    'category': 'Accounting/Accounting',
    'version': '18.0.1.17.0',
    'depends': [
        'account',
        'account_accountant',
        'account_reports',
        'account_batch_payment',
        'sale',
        'purchase',
        'mail',
        'hr_payroll',
        'hr_payroll_account',
        'kc_fiscal_hn_v18',
    ],
    'data': [
        # Seguridad
        'security/kenocia_tesoreria_groups.xml',
        'security/ir.model.access.csv',
        'security/kenocia_tesoreria_rules.xml',
        # Datos base
        'data/kenocia_tesoreria_data.xml',
        # Acciones y menús raíz
        'views/kenocia_dashboard_views.xml',
        'views/kenocia_manual_views.xml',
        'views/kenocia_tesoreria_actions.xml',
        'views/kenocia_tesoreria_config_actions.xml',
        # Secuencias y pagos (vistas antes de acciones enlazadas)
        'views/kenocia_sequence_views.xml',
        'views/kenocia_payment_form_views.xml',
        'views/kenocia_payment_method_views.xml',
        'views/kenocia_payment_list_views.xml',
        'views/kenocia_payment_method_actions.xml',
        'views/kenocia_tesoreria_menu.xml',
        # Adelantos CXC/CXP
        'views/kenocia_advance_payment_views.xml',
        'views/kenocia_advance_payment_list_views.xml',
        # Herencias SO / PO / Facturas
        'views/kenocia_sale_order_views.xml',
        'views/kenocia_purchase_order_views.xml',
        'views/kenocia_account_move_views.xml',
        'views/kenocia_res_company_views.xml',
        # Configuración centralizada de tesorería (vistas)
        'views/kenocia_journal_config_views.xml',
        'views/kenocia_partner_bank_views.xml',
        'views/kenocia_account_config_views.xml',
        'views/kenocia_reconcile_views.xml',
        # Caja Chica
        'views/kenocia_petty_cash_views.xml',
        'views/kenocia_petty_cash_list_views.xml',
        'views/kenocia_petty_cash_menu.xml',
        # Wizards
        'wizards/kenocia_apply_advance_wizard_views.xml',
        'wizards/kenocia_void_wizard_views.xml',
        'wizards/kenocia_report_wizard_views.xml',
        'wizards/kenocia_petty_cash_settlement_views.xml',
        'wizards/kenocia_petty_cash_report_wizard_views.xml',
        'wizards/kenocia_petty_cash_close_wizard_views.xml',
        # Dispersión / pagos masivos (Esc. 1, 2 y 3)
        'wizards/kenocia_mass_payment_wizard_views.xml',
        'wizards/kenocia_vendor_dispersion_wizard_views.xml',
        'wizards/kenocia_payroll_dispersion_wizard_views.xml',
        'views/kenocia_batch_payment_views.xml',
        'views/kenocia_dispersion_menu.xml',
        # Reportes QWeb
        'reports/kenocia_report_payment_receipt.xml',
        'reports/kenocia_report_tesoreria.xml',
        'reports/kenocia_report_advance_receipt.xml',
        'reports/kenocia_report_advance.xml',
        'reports/kenocia_report_petty_cash.xml',
        'reports/kenocia_petty_cash_report_actions.xml',
        'reports/kenocia_petty_cash_operational_report.xml',
        'reports/kenocia_petty_cash_fiscal_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'kenocia_tesoreria_v18/static/src/scss/kenocia_tesoreria.scss',
            'kenocia_tesoreria_v18/static/src/css/kenocia_dashboard.css',
            'kenocia_tesoreria_v18/static/src/js/kenocia_dashboard.js',
            'kenocia_tesoreria_v18/static/src/xml/kenocia_dashboard.xml',
            'kenocia_tesoreria_v18/static/src/css/kenocia_manual.css',
            'kenocia_tesoreria_v18/static/src/js/kenocia_manual_content.js',
            'kenocia_tesoreria_v18/static/src/js/kenocia_manual.js',
            'kenocia_tesoreria_v18/static/src/xml/kenocia_manual.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'sequence': 10,
}
