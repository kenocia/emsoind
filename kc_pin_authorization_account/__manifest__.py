# -*- coding: utf-8 -*-
{
    'name': 'KC Autorización por PIN — Contabilidad',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Exige PIN de empleado antes de publicar/contabilizar un asiento '
               'según reglas configurables',
    'description': """
Módulo-puente que conecta `kc_pin_authorization` con Contabilidad.

Engancha `account.move.action_post` para exigir el PIN de un empleado antes de
publicar (contabilizar) un asiento o factura, SOLO si existe una regla activa
configurada para el documento `account.move` y la operación `post`.

Recomendación: como `action_post` también se invoca en flujos automáticos
(pagos, conciliaciones, etc.), conviene acotar la regla con un dominio
específico, por ejemplo solo facturas de cliente:
[("move_type", "=", "out_invoice")].
    """,
    'author': 'Kenocia (Kenosis Company)',
    'website': 'https://kenocia.com',
    'license': 'LGPL-3',
    'depends': ['account', 'kc_pin_authorization'],
    'data': [
        'views/account_move_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
