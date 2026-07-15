# -*- coding: utf-8 -*-
{
    'name': 'KC Autorización por PIN — Compras',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Purchase',
    'summary': 'Exige PIN de empleado antes de confirmar una orden de compra '
               'según reglas configurables',
    'description': """
Módulo-puente que conecta `kc_pin_authorization` con Compras.

Engancha `purchase.order.button_confirm` para exigir el PIN de un empleado antes
de confirmar una orden de compra, SOLO si existe una regla activa configurada
para el documento `purchase.order` y la operación `confirm`.
    """,
    'author': 'Kenocia (Kenosis Company)',
    'website': 'https://kenocia.com',
    'license': 'LGPL-3',
    'depends': ['purchase', 'kc_pin_authorization'],
    'data': [
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
