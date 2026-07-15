# -*- coding: utf-8 -*-
"""Re-sincroniza líneas de RP con OV evitando emparejamientos duplicados."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Entry = env['kc.production.entry']
    entries = Entry.search([
        ('sale_order_id', '!=', False),
        ('state', 'in', ['draft', 'confirmed']),
        ('reversal_of_id', '=', False),
    ])
    for entry in entries:
        entry._kc_sync_all_lines_from_sale_order()

    _logger.info(
        'kc_manual_production 18.0.1.13.0: %s RP re-sincronizados con la OV.',
        len(entries),
    )
