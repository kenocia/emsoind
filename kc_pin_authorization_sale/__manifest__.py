# -*- coding: utf-8 -*-
{
    'name': 'KC Autorización por PIN — Ventas',
    'version': '18.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Exige PIN de empleado antes de confirmar un pedido de venta '
               'según reglas configurables',
    'description': """
Módulo-puente que conecta `kc_pin_authorization` con Ventas.

Engancha `sale.order.action_confirm` para exigir el PIN de un empleado antes de
confirmar un pedido, SOLO si existe una regla activa configurada para el
documento `sale.order` y la operación `confirm`.
    """,
    'author': 'Kenocia (Kenosis Company)',
    'website': 'https://kenocia.com',
    'license': 'LGPL-3',
    'depends': ['sale', 'kc_pin_authorization'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
