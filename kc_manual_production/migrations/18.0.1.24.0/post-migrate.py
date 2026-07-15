# -*- coding: utf-8 -*-
"""Centros de trabajo por defecto, backfill work_center_id y log de backlog."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Line = env['kc.production.line']
    Center = env['kc.work.center']
    Entry = env['kc.production.entry']
    Consumption = env['kc.production.consumption']

    created = 0
    for line in Line.search([('active', '=', True)]):
        center = Center.search([
            ('production_line_id', '=', line.id),
            ('name', '=', 'General'),
        ], limit=1)
        if not center:
            center = Center.create({
                'name': 'General',
                'code': (line.code or 'GEN')[:16],
                'production_line_id': line.id,
                'state': 'active',
                'sequence': 10,
            })
            created += 1

        entries = Entry.search([
            ('production_line_id', '=', line.id),
            ('work_center_id', '=', False),
        ])
        if entries:
            entries.write({'work_center_id': center.id})

        cmps = Consumption.search([
            ('production_line_id', '=', line.id),
            ('work_center_id', '=', False),
        ])
        if cmps:
            cmps.write({'work_center_id': center.id})

    # Recrear vista SQL del backlog y estimar filas con saldo.
    Backlog = env['kc.production.backlog']
    Backlog.init()
    pending_rows = Backlog.search_count([('raw_pending_qty', '>', 0)])

    _logger.info(
        'kc_manual_production 18.0.1.24.0: %s centro(s) "General" creados; '
        '%s fila(s) de backlog con saldo (ov - producido) > 0.',
        created,
        pending_rows,
    )
