# -*- coding: utf-8 -*-
"""
Carga inventario PT Compra/Venta — Opción A — 30/06/2026

- 20 productos → ESI/Bodega MP (cuenta 11116)
- 1 producto EMG160 → ESI/Bodega PT (cuenta 11118)
- Tracking por lote: {default_code}-INV20260630
- Fuente: Producto Compra Venta 2026.xlsx
"""
from __future__ import annotations

import openpyxl

INVENTORY_DATE = '2026-06-30'
LOT_SUFFIX = 'INV20260630'
INVENTORY_NAME = 'Toma física PT Compra-Venta 30/06/2026'
XLSX_PATH = '/opt/odoo/src/custom/emsoind_migration/Producto Compra Venta 2026.xlsx'


def _log(msg):
    print(msg, flush=True)


def _resolve_product(name):
    Product = env['product.template']
    pt = Product.search([('name', '=', name)], limit=1)
    if not pt:
        pt = Product.search([('name', 'ilike', name)], limit=1)
    if not pt:
        short = name.split(',')[0].strip()
        pt = Product.search([('name', 'ilike', short)], limit=1)
    if not pt:
        raise ValueError(f'Producto no encontrado: {name}')
    return pt


def _bodega_for_product(pt):
    val_code = pt.categ_id.property_stock_valuation_account_id.code
    if val_code == '11118':
        return 'ESI/Bodega PT'
    return 'ESI/Bodega MP'


def _read_rows():
    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True, read_only=True)
    ws = wb.active
    rows = []
    for r in ws.iter_rows(values_only=True):
        if not r[0] or str(r[0]).strip() == 'Nombre':
            continue
        rows.append({
            'name': str(r[0]).strip(),
            'sale_price': float(r[1] or 0),
            'cost': float(r[2] or 0),
            'qty': float(r[3] or 0),
        })
    return rows


def prepare_products(rows):
    _log('\n=== PASO 1: PREPARAR PRODUCTOS (tracking + costo) ===')
    updated = 0
    for row in rows:
        pt = _resolve_product(row['name'])
        pp = pt.product_variant_id
        vals = {}
        if pt.tracking != 'lot':
            vals['tracking'] = 'lot'
        if not pt.lot_valuated:
            vals['lot_valuated'] = True
        if vals:
            pt.write(vals)
        if row['cost'] and abs((pp.standard_price or 0) - row['cost']) > 0.0001:
            pt.with_company(env.company).write({'standard_price': row['cost']})
        _log(
            f'  [OK] {pp.default_code} | lot | cost L.{row["cost"]:,.4f} | '
            f'{_bodega_for_product(pt)}'
        )
        updated += 1
    env.flush_all()
    env.cr.commit()
    _log(f'Productos preparados: {updated}/{len(rows)}')
    return updated


def load_inventory(rows):
    _log('\n=== PASO 2: CARGA INVENTARIO CON LOTE ===')
    Location = env['stock.location']
    Quant = env['stock.quant'].sudo()
    Lot = env['stock.lot']
    applied = 0
    errors = []
    total_val = 0.0

    inv_ctx = {
        'inventory_mode': True,
        'inventory_name': INVENTORY_NAME,
        'force_period_date': INVENTORY_DATE,
    }

    for index, row in enumerate(rows, start=2):
        qty = row['qty']
        if qty <= 0:
            continue
        try:
            pt = _resolve_product(row['name'])
            pp = pt.product_variant_id
            code = pp.default_code
            if not code:
                raise ValueError('Producto sin default_code')

            loc_name = _bodega_for_product(pt)
            location = Location.search([
                ('complete_name', '=', loc_name),
                ('usage', '=', 'internal'),
            ], limit=1)
            if not location:
                raise ValueError(f'Ubicación no encontrada: {loc_name}')

            lot_name = f'{code}-{LOT_SUFFIX}'
            lot = Lot.search([
                ('name', '=', lot_name),
                ('product_id', '=', pp.id),
                ('company_id', 'in', [env.company.id, False]),
            ], limit=1)
            if not lot:
                lot = Lot.create({
                    'name': lot_name,
                    'product_id': pp.id,
                    'company_id': env.company.id,
                })

            existing = Quant.search([
                ('product_id', '=', pp.id),
                ('location_id', '=', location.id),
                ('lot_id', '=', lot.id),
                ('company_id', '=', env.company.id),
            ], limit=1)

            ctx = dict(inv_ctx)
            vals = {
                'inventory_quantity': qty,
                'accounting_date': INVENTORY_DATE,
            }
            if existing:
                existing.with_context(ctx).write(vals)
                existing.with_context(ctx)._apply_inventory()
            else:
                quant = Quant.with_context(ctx).create({
                    'product_id': pp.id,
                    'location_id': location.id,
                    'lot_id': lot.id,
                    **vals,
                })
                quant.with_context(ctx)._apply_inventory()

            total_val += qty * (pp.standard_price or 0)
            applied += 1
            _log(
                f'  [OK] {lot_name} | {qty:,.0f} uds | {loc_name} | '
                f'L.{qty * (pp.standard_price or 0):,.2f}'
            )
        except Exception as exc:
            errors.append(f'Fila {index} ({row.get("name", "?")}): {exc}')

    env.flush_all()
    env.cr.commit()
    _log(f'Filas aplicadas: {applied}/{len(rows)}')
    _log(f'Valor cargado (qty x costo): L.{total_val:,.2f}')
    if errors:
        _log(f'Errores: {len(errors)}')
        for err in errors:
            _log(f'  {err}')
    return applied, errors, total_val


def verify():
    _log('\n=== PASO 3: VERIFICACIÓN ===')
    for loc_name in ['ESI/Bodega MP', 'ESI/Bodega PT']:
        loc = env['stock.location'].search([('complete_name', '=', loc_name)], limit=1)
        quants = env['stock.quant'].sudo().search([
            ('location_id', '=', loc.id),
            ('quantity', '!=', 0),
            ('lot_id', '!=', False),
        ])
        val = sum(q.quantity * (q.product_id.standard_price or 0) for q in quants)
        _log(f'  {loc_name}: {len(quants)} quants c/lote | L.{val:,.2f}')

    Account = env['account.account']
    for code in ['11113', '11116', '11118', '11120']:
        acc = Account.search([('code', '=', code)], limit=1)
        if not acc:
            continue
        lines = env['account.move.line'].search([
            ('account_id', '=', acc.id),
            ('parent_state', '=', 'posted'),
        ])
        balance = sum(lines.mapped('balance'))
        _log(f'  {code}: saldo L.{balance:,.2f}')

    new_moves = env['account.move'].search_count([
        ('date', '=', INVENTORY_DATE),
        ('ref', 'ilike', INVENTORY_NAME),
        ('state', '=', 'posted'),
    ])
    _log(f'  Asientos STJ nuevos ({INVENTORY_NAME}): {new_moves}')


_log('=' * 72)
_log(f'EMSOIND — PT Compra/Venta Opción A | {INVENTORY_DATE}')
_log('=' * 72)

rows = _read_rows()
prepare_products(rows)
load_inventory(rows)
verify()
_log('\n=== FIN ===')
