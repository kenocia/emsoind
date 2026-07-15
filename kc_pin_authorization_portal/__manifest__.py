# -*- coding: utf-8 -*-
{
    'name': 'KC Autorización por PIN — Portal',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'summary': 'Permite a usuarios del portal (con empleado vinculado) cambiar '
               'su propio PIN de autorización desde "Mi cuenta"',
    'description': """
Módulo-puente que añade al portal una página "Cambiar mi PIN" para que los
empleados cuyo usuario es de portal puedan definir/cambiar su PIN de
autorización sin acceso al backend.
    """,
    'author': 'Kenocia (Kenosis Company)',
    'website': 'https://kenocia.com',
    'license': 'LGPL-3',
    'depends': ['portal', 'kc_pin_authorization'],
    'data': [
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'kc_pin_authorization_portal/static/src/scss/portal_pin.scss',
            'kc_pin_authorization_portal/static/src/js/portal_pin.js',
        ],
    },
    'installable': True,
    'auto_install': False,
}
