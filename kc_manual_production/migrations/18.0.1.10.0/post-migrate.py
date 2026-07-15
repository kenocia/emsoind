# -*- coding: utf-8 -*-
"""Rellena lote y especificaciones técnicas en líneas de RP desde la OV vinculada."""

import logging

_logger = logging.getLogger(__name__)


def _kc_resolve_sale_line(entry, line):
    """Resuelve la línea de OV origen de una línea de RP."""
    SaleLine = entry.env['sale.order.line']
    if line.sale_order_line_id:
        return line.sale_order_line_id
    if not entry.sale_order_id or not line.product_id:
        return SaleLine

    candidates = entry.sale_order_id.order_line.filtered(
        lambda l: not l.display_type and l.product_id == line.product_id
    )
    if not candidates:
        return SaleLine

    # Mismo producto con varias especificaciones: emparejar por cantidad.
    if line.qty:
        by_qty = candidates.filtered(
            lambda l: l.product_uom_qty == line.qty
        )
        if len(by_qty) == 1:
            return by_qty
        if len(by_qty) > 1 and line.kc_unit_cost:
            Lot = entry.env['stock.lot']
            for sol in by_qty:
                ov_lot = getattr(sol, 'lot_id', False)
                tech_key = getattr(sol, 'technical_key', False)
                cost = Lot._kc_resolve_unit_cost(
                    sol.product_id,
                    technical_key=tech_key,
                    lot=ov_lot,
                    company=entry.company_id,
                )
                if cost and abs(cost - line.kc_unit_cost) < 0.0001:
                    return sol

    # Respaldo: clave técnica si ya existe parcialmente en la línea de RP.
    if line.kc_technical_key:
        by_key = candidates.filtered(
            lambda l: getattr(l, 'technical_key', False) == line.kc_technical_key
        )
        if len(by_key) == 1:
            return by_key

    if len(candidates) == 1:
        return candidates[:1]
    return SaleLine


def _kc_vals_from_sale_line(sol):
    """Extrae lote y especificaciones de una línea de OV."""
    ov_lot = getattr(sol, 'lot_id', False)
    technical_key = getattr(sol, 'technical_key', False) or False
    technical_desc = getattr(sol, 'technical_description', False) or False
    if not technical_desc and ov_lot:
        technical_desc = getattr(ov_lot, 'technical_description', False) or False
    vals = {}
    if ov_lot:
        vals['lot_id'] = ov_lot.id
    if technical_key:
        vals['kc_technical_key'] = technical_key
    if technical_desc:
        vals['kc_technical_description'] = technical_desc
    return vals


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

    updated_lines = 0
    linked_lines = 0
    for entry in entries:
        for line in entry.line_ids:
            needs_lot = not line.lot_id
            needs_key = not line.kc_technical_key
            needs_desc = not line.kc_technical_description
            if not (needs_lot or needs_key or needs_desc):
                continue

            sol = _kc_resolve_sale_line(entry, line)
            if not sol:
                continue

            vals = _kc_vals_from_sale_line(sol)
            write_vals = {}
            if needs_lot and vals.get('lot_id'):
                write_vals['lot_id'] = vals['lot_id']
            if needs_key and vals.get('kc_technical_key'):
                write_vals['kc_technical_key'] = vals['kc_technical_key']
            if needs_desc and vals.get('kc_technical_description'):
                write_vals['kc_technical_description'] = vals['kc_technical_description']
            if not line.sale_order_line_id:
                write_vals['sale_order_line_id'] = sol.id
                linked_lines += 1

            if write_vals:
                line.write(write_vals)
                updated_lines += 1

    _logger.info(
        'kc_manual_production 18.0.1.10.0: %s líneas de RP actualizadas '
        '(%s vinculadas a línea de OV).',
        updated_lines,
        linked_lines,
    )
