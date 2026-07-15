# -*- coding: utf-8 -*-
"""Rellena kc_unit_cost almacenado en líneas de RP existentes."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Line = env['kc.production.entry.line'].search([])
    Lot = env['stock.lot']
    updated = 0
    for line in Line:
        if line.kc_unit_cost:
            continue
        if not line.product_id:
            continue
        cost = Lot._kc_resolve_unit_cost(
            line.product_id,
            technical_key=line.kc_technical_key,
            lot=line.lot_id,
            company=line.entry_id.company_id,
        )
        if cost:
            line.kc_unit_cost = cost
            updated += 1
    _logger.info(
        'kc_manual_production 18.0.1.9.0: %s líneas de RP con costo sugerido migrado.',
        updated,
    )
