# -*- coding: utf-8 -*-
{
    'name': 'Kenocia Gastos Fiscal HN + Anticipo Empleado',
    'summary': 'Tropicalización fiscal de gastos y anticipos a empleados para Honduras',
    'description': """
        Gastos de empleado con validez fiscal SAR (libro de compras) y control
        de anticipos por liquidar, independiente de caja chica.
    """,
    'author': 'Kenocia (Kenosis Company)',
    'website': 'https://kenocia.com/',
    'license': 'LGPL-3',
    'category': 'Human Resources/Expenses',
    'version': '18.0.2.0.0',
    'depends': [
        'hr_expense',
        'kc_fiscal_hn_v18',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/kc_expense_advance_views.xml',
        'views/hr_expense_views.xml',
        'views/hr_expense_sheet_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/kc_expense_advance_close_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
