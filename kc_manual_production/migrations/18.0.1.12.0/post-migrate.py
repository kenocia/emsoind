# -*- coding: utf-8 -*-
"""Restaura especificaciones técnicas en líneas de RP confirmadas/borrador."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Line = env['kc.production.entry.line']
    lines = Line.search([
        ('entry_id.sale_order_id', '!=', False),
        ('entry_id.state', 'in', ['draft', 'confirmed']),
        ('entry_id.reversal_of_id', '=', False),
    ])

    updated = 0
    for line in lines:
        before = line.kc_technical_description
        line._kc_ensure_sale_line_link()
        line._kc_refresh_technical_description()
        if line.kc_technical_description != before:
            updated += 1

    _logger.info(
        'kc_manual_production 18.0.1.12.0: %s líneas de RP con especificaciones restauradas.',
        updated,
    )
