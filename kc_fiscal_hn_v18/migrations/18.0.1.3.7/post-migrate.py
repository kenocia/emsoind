# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Recalcula estado/alertas CAI tras corregir umbral de correlativos."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    sequences = env['ir.sequence'].search([('is_fiscal', '=', True)])
    if not sequences:
        return
    sequences._compute_rango_cai_stats()
    ranges = env['ir.sequence.date_range'].search([
        ('sequence_id.is_fiscal', '=', True),
    ])
    if ranges:
        ranges._compute_rango_usage()
