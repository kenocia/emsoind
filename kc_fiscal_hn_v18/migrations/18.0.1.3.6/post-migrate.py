# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Recalcula consumo/alertas CAI tras corregir depends y fórmulas."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    sequences = env['ir.sequence'].search([('is_fiscal', '=', True)])
    if not sequences:
        return
    sequences._recompute_recordset([
        'active_cai_name',
        'active_cai_disponibles',
        'active_cai_consumidos',
        'active_cai_total',
        'active_cai_uso_label',
        'active_cai_vence',
        'active_cai_vence_label',
        'fiscal_list_estado',
        'fiscal_list_vencida',
        'fiscal_list_alerta',
        'rango_cai_count',
    ])
    ranges = env['ir.sequence.date_range'].search([
        ('sequence_id.is_fiscal', '=', True),
    ])
    if ranges:
        ranges._recompute_recordset([
            'disponibles',
            'uso_porcentaje',
            'dias_restantes',
            'es_vigente',
            'estado_rango',
        ])
