# -*- coding: utf-8 -*-
{
    'name': 'KC Autorización por PIN — Producción Manual',
    'version': '18.0.1.2.0',
    'category': 'Inventory/Inventory',
    'summary': 'Exige PIN de empleado antes de confirmar, validar o revertir un '
               'Registro de Producción (RP) o un Consumo de Materia Prima (CMP) '
               'según reglas configurables',
    'description': """
Módulo-puente que conecta `kc_pin_authorization` con `kc_manual_production`.

Engancha el Registro de Producción (`kc.production.entry`):
- `action_confirm` → operación `confirm`
- `action_validate` → operación `validate` (impacta inventario)
- `action_open_reversal_wizard` → operación `reverse` (reversión de inventario)

Engancha el Consumo de Materia Prima (`kc.production.consumption`):
- `action_confirm` → operación `confirm`
- `action_validate` → operación `validate` (impacta inventario)
- `action_open_reversal_wizard` → operación `reverse` (reversión de inventario)

Engancha los asistentes de reversión (al pulsar "Confirmar Reversión"):
- `kc.production.entry.reversal.wizard.action_confirm_reversal` → operación `validate`
- `kc.production.consumption.reversal.wizard.action_confirm_reversal` → operación `validate`

El PIN se exige solo si existe una regla activa para el modelo y la operación
correspondiente (se configura en Ajustes ▸ Autorización por PIN). Para exigir
PIN al revertir se puede usar cualquiera de los dos enganches: la regla sobre el
RP/CMP con operación "Revertir" (pide el PIN al abrir el asistente) o la regla
sobre el "Asistente de Reversión..." con operación "Validar" (pide el PIN al
confirmar la reversión).
    """,
    'author': 'Kenocia (Kenosis Company)',
    'website': 'https://kenocia.com',
    'license': 'LGPL-3',
    'depends': ['kc_manual_production', 'kc_pin_authorization'],
    'data': [
        'views/kc_production_entry_views.xml',
        'views/kc_production_consumption_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
