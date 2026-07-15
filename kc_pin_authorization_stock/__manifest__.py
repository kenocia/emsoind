# -*- coding: utf-8 -*-
{
    'name': 'KC Autorización por PIN — Inventario',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Exige PIN de empleado antes de validar transferencias '
               '(recepción, despacho, internas) según reglas configurables',
    'description': """
Módulo-puente que conecta `kc_pin_authorization` con Inventario.

Engancha `stock.picking.button_validate` para exigir el PIN de un empleado
antes de validar una transferencia, SOLO si existe una regla activa configurada
para el documento `stock.picking` y la operación `validate`.

El alcance (recepción, despacho, internas o un almacén concreto) se define con
el dominio de la regla, por ejemplo:
- Recepción:  [("picking_type_code", "=", "incoming")]
- Despacho:   [("picking_type_code", "=", "outgoing")]
- Internas:   [("picking_type_code", "=", "internal")]
    """,
    'author': 'Kenocia (Kenosis Company)',
    'website': 'https://kenocia.com',
    'license': 'LGPL-3',
    'depends': ['stock', 'kc_pin_authorization'],
    'data': [
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
