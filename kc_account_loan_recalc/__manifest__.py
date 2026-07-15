# -*- coding: utf-8 -*-
{
    'name': 'KC Préstamos: Recalcular amortización',
    'summary': 'Recalcular amortización respetando la tasa y opciones del asistente',
    'version': '18.0.3.0.0',
    'category': 'Accounting',
    'author': 'KENOCIA',
    'license': 'LGPL-3',
    'depends': ['account_loans'],
    'data': [
        'views/account_loan_views.xml',
        'views/account_loan_compute_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
}
