# -*- coding: utf-8 -*-
"""Asigna el lote creado en ventas a líneas de RP por producto/especificación."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Entry = env['kc.production.entry']
    Line = env['kc.production.entry.line']
    entries = Entry.search([
        ('sale_order_id', '!=', False),
        ('state', 'in', ['draft', 'confirmed']),
        ('reversal_of_id', '=', False),
    ])

    updated_lines = 0
    for entry in entries:
        for line in entry.line_ids:
            sol = line.sale_order_line_id
            if not sol:
                sol = Line._kc_find_sale_order_line(
                    entry.sale_order_id,
                    line.product_id,
                    qty=line.qty,
                    technical_key=line.kc_technical_key,
                    kc_unit_cost=line.kc_unit_cost,
                )
            if not sol:
                continue

            lot = Line._kc_get_lot_from_sale_line(sol)
            desc = getattr(sol, 'technical_description', False)
            if not desc and lot:
                desc = getattr(lot, 'technical_description', False)
            tech_key = getattr(sol, 'technical_key', False) or False

            write_vals = {}
            if lot and line.lot_id != lot:
                write_vals['lot_id'] = lot.id
            if tech_key and line.kc_technical_key != tech_key:
                write_vals['kc_technical_key'] = tech_key
            if desc and line.kc_technical_description != desc:
                write_vals['kc_technical_description'] = desc
            if line.sale_order_line_id != sol:
                write_vals['sale_order_line_id'] = sol.id

            if write_vals:
                line.write(write_vals)
                updated_lines += 1

    _logger.info(
        'kc_manual_production 18.0.1.11.0: %s líneas de RP con lote de OV asignado.',
        updated_lines,
    )
