# -*- coding: utf-8 -*-
"""
Carga inventario PT Ficha Técnica — 30/06/2026

- 54 configuraciones con stock → ESI/Bodega PT (cuenta 11118)
- Lote: Auto Odoo (build_lot_name + secuencia stock.lot.technical)
- Costo: Excel → lot.standard_price (lot_valuated)
- Fuente: Configuración técnica de producto (matriz).xlsx
"""
from __future__ import annotations

import openpyxl

INVENTORY_DATE = '2026-06-30'
LOCATION_NAME = 'ESI/Bodega PT'
INVENTORY_NAME = 'Inventario inicial PT 30/06/2026'
XLSX_PATH = '/opt/odoo/src/custom/emsoind_migration/pt_ficha_tecnica_matriz.xlsx'


def _log(msg):
    print(msg, flush=True)


def _read_rows():
    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True, read_only=True)
    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not all_rows:
        raise ValueError('Excel vacío')
    headers = all_rows[0]
    ci = next(i for i, h in enumerate(headers) if 'configuraci' in str(h).lower())
    qi = next(i for i, h in enumerate(headers) if 'cantidad' in str(h).lower())
    coi = next(i for i, h in enumerate(headers) if 'costo' in str(h).lower())
    rows = []
    for excel_row, raw in enumerate(all_rows[1:], start=2):
        qty = float(raw[qi] or 0)
        if qty <= 0:
            continue
        rows.append({
            'row': excel_row,
            'configuration_key': str(raw[ci] or '').strip(),
            'qty': qty,
            'cost': float(raw[coi] or 0),
        })
    return rows


def prepare_products(rows):
    _log('\n=== PASO 1: VERIFICAR PRODUCTOS (tracking + lot_valuated) ===')
    Config = env['product.technical.configuration']
    seen = set()
    updated = 0
    for row in rows:
        cfg = Config.search([
            ('configuration_key', '=', row['configuration_key']),
            ('active', '=', True),
        ], limit=1)
        if not cfg:
            raise ValueError(f"Config no encontrada: {row['configuration_key']}")
        pt = cfg.product_tmpl_id
        if pt.id in seen:
            continue
        seen.add(pt.id)
        vals = {}
        if pt.tracking != 'lot':
            vals['tracking'] = 'lot'
        if not pt.lot_valuated:
            vals['lot_valuated'] = True
        if vals:
            pt.write(vals)
            updated += 1
        _log(f'  [OK] {pt.default_code} | tracking=lot | lot_valuated=True')
    env.flush_all()
    env.cr.commit()
    _log(f'Productos revisados: {len(seen)} | actualizados: {updated}')
    return len(seen)


def load_inventory(rows):
    _log('\n=== PASO 2: CARGA INVENTARIO (lote Auto Odoo) ===')
    Lot = env['stock.lot']
    Quant = env['stock.quant'].sudo()
    Config = env['product.technical.configuration']
    company = env.company

    location = Lot._kc_resolve_inventory_location(
        None, location_name=LOCATION_NAME, company=company,
    )
    if not location:
        raise ValueError(f'Ubicación no encontrada: {LOCATION_NAME}')
    _log(f'  Ubicación: {location.complete_name}')

    inv_ctx = {
        'inventory_mode': True,
        'inventory_name': INVENTORY_NAME,
        'force_period_date': INVENTORY_DATE,
    }

    applied = 0
    lots_created = 0
    lots_reused = 0
    errors = []
    total_val = 0.0

    for row in rows:
        try:
            cfg = Config.search([
                ('configuration_key', '=', row['configuration_key']),
                ('active', '=', True),
            ], limit=1)
            if not cfg:
                raise ValueError('Configuración no encontrada')

            product = cfg.product_tmpl_id.product_variant_id
            if product.tracking != 'lot':
                raise ValueError(f'{product.display_name} sin tracking por lote')

            unit_cost = row['cost']
            if unit_cost <= 0:
                raise ValueError('Costo unitario debe ser > 0')

            lot, created = Lot._get_or_create_inventory_lot(
                cfg,
                company,
                lot_name=None,
                inventory_date=INVENTORY_DATE,
                unit_cost=unit_cost,
            )
            if created:
                lots_created += 1
            else:
                lots_reused += 1

            existing_quant = Quant.search([
                ('product_id', '=', product.id),
                ('location_id', '=', location.id),
                ('lot_id', '=', lot.id),
                ('company_id', '=', company.id),
            ], limit=1)

            qty = row['qty']
            lot_cost = lot.standard_price or unit_cost
            if existing_quant:
                target_qty = existing_quant.quantity + qty
                existing_quant.with_context(inv_ctx).write({
                    'inventory_quantity': target_qty,
                })
                existing_quant.with_context(inv_ctx)._apply_inventory()
            else:
                quant = Quant.with_context(inv_ctx).create({
                    'product_id': product.id,
                    'location_id': location.id,
                    'lot_id': lot.id,
                    'inventory_quantity': qty,
                })
                quant.with_context(inv_ctx)._apply_inventory()

            line_val = qty * lot_cost
            total_val += line_val
            applied += 1
            _log(
                f'  [OK] {lot.name} | {qty:,.0f} uds | '
                f'cost L.{lot_cost:,.2f} | L.{line_val:,.2f} | {row["configuration_key"]}'
            )
        except Exception as exc:
            errors.append(f'Fila {row["row"]} ({row["configuration_key"]}): {exc}')

    env.flush_all()
    env.cr.commit()
    _log(f'Filas aplicadas: {applied}/{len(rows)}')
    _log(f'Lotes creados: {lots_created} | reutilizados: {lots_reused}')
    _log(f'Valor cargado (qty x costo lote): L.{total_val:,.2f}')
    if errors:
        _log(f'Errores: {len(errors)}')
        for err in errors:
            _log(f'  {err}')
    return applied, errors, total_val, lots_created


def verify():
    _log('\n=== PASO 3: VERIFICACIÓN ===')
    loc = env['stock.location'].search([
        ('complete_name', '=', LOCATION_NAME),
    ], limit=1)
    quants = env['stock.quant'].sudo().search([
        ('location_id', '=', loc.id),
        ('quantity', '!=', 0),
        ('lot_id.source_type', '=', 'inventory'),
    ])
    val = 0.0
    for q in quants:
        cost = q.lot_id.standard_price if q.lot_id and q.product_id.lot_valuated else q.product_id.standard_price
        val += q.quantity * (cost or 0)
    _log(f'  {LOCATION_NAME}: {len(quants)} quants ficha técnica | L.{val:,.2f}')

    Account = env['account.account']
    for code in ['11113', '11116', '11118', '11120']:
        acc = Account.search([('code', '=', code)], limit=1)
        if not acc:
            continue
        env.cr.execute(
            """
            SELECT COALESCE(SUM(debit - credit), 0)
            FROM account_move_line
            WHERE account_id = %s AND parent_state = 'posted'
            """,
            [acc.id],
        )
        balance = env.cr.fetchone()[0]
        _log(f'  {code}: saldo L.{balance:,.2f}')

    inv_total = 0.0
    for code in ['11113', '11116', '11118']:
        acc = Account.search([('code', '=', code)], limit=1)
        env.cr.execute(
            "SELECT COALESCE(SUM(debit-credit),0) FROM account_move_line "
            "WHERE account_id=%s AND parent_state='posted'",
            [acc.id],
        )
        inv_total += env.cr.fetchone()[0]
    acc20 = Account.search([('code', '=', '11120')], limit=1)
    env.cr.execute(
        "SELECT COALESCE(SUM(debit-credit),0) FROM account_move_line "
        "WHERE account_id=%s AND parent_state='posted'",
        [acc20.id],
    )
    bal20 = env.cr.fetchone()[0]
    _log(f'  Inventario total (11113+11116+11118): L.{inv_total:,.2f}')
    _log(f'  Check inv+11120: L.{inv_total + bal20:,.2f}')

    new_moves = env['account.move'].search_count([
        ('date', '=', INVENTORY_DATE),
        ('ref', 'ilike', INVENTORY_NAME),
        ('state', '=', 'posted'),
    ])
    _log(f'  Asientos STJ ({INVENTORY_NAME}): {new_moves}')


_log('=' * 72)
_log(f'EMSOIND — PT Ficha Técnica | {INVENTORY_DATE} | Lote Auto Odoo')
_log('=' * 72)

rows = _read_rows()
_log(f'Filas con stock en Excel: {len(rows)}')
prepare_products(rows)
load_inventory(rows)
verify()
_log('\n=== FIN ===')
