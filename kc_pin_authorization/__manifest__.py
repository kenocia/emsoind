# -*- coding: utf-8 -*-
{
    'name': 'KC Autorización por PIN',
    'version': '18.0.1.1.0',
    'category': 'Tools',
    'summary': 'Autorización por PIN de empleado reutilizable para cualquier acción, '
               'con rastro (empleado, fecha/hora), log central y registro en el chatter',
    'description': """
Módulo genérico y reutilizable de autorización por PIN.

Cualquier módulo puede exigir que un empleado autorice una acción introduciendo
su PIN (el mismo `pin` de hr.employee que usa el POS). Provee:

- Mixin `kc.pin.authorization.mixin`: añade campos de rastro
  (empleado autorizante, fecha/hora, usuario de sesión), registro en el chatter
  del documento y un helper para abrir el diálogo de PIN.
- Servicio `kc.pin.authorization.verify_pin`: valida el PIN de forma segura
  (comparación de tiempo constante) con bloqueo temporal por intentos fallidos.
- Log central `kc.pin.authorization.log`: auditoría de todos los intentos
  (exitosos y fallidos).
- Diálogo OWL atractivo con teclado numérico que bloquea el fondo.
    """,
    'author': 'Kenocia (Kenosis Company)',
    'website': 'https://kenocia.com',
    'license': 'LGPL-3',
    'depends': ['mail', 'hr'],
    'data': [
        'security/ir.model.access.csv',
        'views/pin_authorization_rule_views.xml',
        'views/pin_authorization_log_views.xml',
        'views/pin_authorization_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_users_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'kc_pin_authorization/static/src/pin_pad/pin_pad.js',
            'kc_pin_authorization/static/src/pin_pad/pin_pad.xml',
            'kc_pin_authorization/static/src/pin_pad/pin_pad.scss',
        ],
    },
    'application': False,
    'installable': True,
    'auto_install': False,
}
