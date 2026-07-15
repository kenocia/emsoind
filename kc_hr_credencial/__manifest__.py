# -*- coding: utf-8 -*-
{
    'name': 'KC Credencial de Empleado',
    'version': '18.0.1.0.0',
    'summary': 'Asignación automática del ID de credencial del empleado y '
               'sincronización con la referencia del contacto',
    'description': """
KC Credencial de Empleado
=========================

Gestiona el identificador único (credencial) del empleado de forma
independiente del módulo fiscal:

* Campo "ID de Credencial" autogenerado por secuencia (formato EMP-0000),
  de solo lectura (sin edición manual).
* Unicidad garantizada (incluye empleados archivados).
* Sincronización automática hacia el campo "Referencia" (ref) del contacto
  asociado al empleado. La credencial del EMPLEADO tiene prioridad sobre la
  numeración automática de contactos.
""",
    'author': 'Kenocia (Kenosis Company)',
    'website': 'https://kenocia.com',
    'license': 'LGPL-3',
    'category': 'Human Resources/Employees',
    'depends': ['hr'],
    'data': [
        'data/ir_sequence_data.xml',
        'views/hr_employee_views.xml',
        'data/init.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
