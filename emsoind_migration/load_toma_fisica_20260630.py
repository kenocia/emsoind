# -*- coding: utf-8 -*-
"""
Toma física EMSOIND — 30/06/2026

1. Actualiza standard_price (regla max: Excel > Odoo) en 7 productos.
2. Carga inventario desde EMSOIND_TomaFisica_CARGA_Corregido.xlsx

Excluidos: EMG010, SEM500 (carga PT).
Excel corregido: 38 MP reubicados a ESI/Bodega MP.
"""
from __future__ import annotations

import openpyxl

INVENTORY_DATE = '2026-06-30'
INVENTORY_NAME = 'Toma física INSUMOS/MP 30/06/2026'
XLSX_PATH = '/opt/odoo/src/custom/emsoind_migration/EMSOIND_TomaFisica_CARGA_Corregido.xlsx'

EXCLUDED_DEFAULT_CODES = frozenset({'EMG010', 'SEM500'})
EXCLUDED_XML_IDS = frozenset({
    '__export__.product_template_6581_b897faf0',  # SEM500
})

# Excel > Odoo con impacto (regla acordada)
COST_UPDATES = {
    'ELT100': 1497.96,
    'PIN510': 1445.982,
    'EQM590': 19.13,
    'DIS020': 29.565,
    'GAS115': 248.75,
}
COST_UPDATES_BY_XML = {
    '__export__.product_template_7045_ab2f9a47': 190.0,   # AGUA DESTILADA
    '__export__.product_template_7046_29ff7baf': 125.0,   # LIMPIA BRISAS
}


def _log(msg):
    print(msg, flush=True)


def _read_rows():
    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(h).strip() if h else '' for h in rows[0]]
    data = []
    for r in rows[1:]:
        if not any(c is not None and str(c).strip() for c in r):
            continue
        data.append(dict(zip(headers, r)))
    return data


def update_costs():
    _log('\n=== PASO 1: ACTUALIZAR COSTOS (Excel > Odoo) ===')
    Product = env['product.product']
    updated = 0
    expected = len(COST_UPDATES) + len(COST_UPDATES_BY_XML)

    for code, new_cost in COST_UPDATES.items():
        pp = Product.search([('default_code', '=', code)], limit=1)
        if not pp:
            _log(f'  [ERROR] Producto no encontrado: {code}')
            continue
        old = pp.standard_price
        pp.product_tmpl_id.with_company(env.company).write({'standard_price': new_cost})
        _log(f'  [OK] {code} | {old:.4f} -> {new_cost:.4f}')
        updated += 1

    for xml_id, new_cost in COST_UPDATES_BY_XML.items():
        product = env.ref(xml_id, raise_if_not_found=False)
        if not product:
            _log(f'  [ERROR] XML-ID no encontrado: {xml_id}')
            continue
        pp = product.product_variant_id if product._name == 'product.template' else product
        old = pp.standard_price
        pp.product_tmpl_id.with_company(env.company).write({'standard_price': new_cost})
        label = pp.default_code or product.display_name[:40]
        _log(f'  [OK] {label} | {old:.4f} -> {new_cost:.4f}')
        updated += 1

    env.flush_all()
    env.cr.commit()
    _log(f'Actualizados: {updated}/{expected}')
    return updated


def load_inventory():
    _log('\n=== PASO 2: CARGA TOMA FÍSICA ===')
    Location = env['stock.location']
    Quant = env['stock.quant'].sudo()
    rows = _read_rows()
    applied = 0
    skipped = 0
    errors = []
    total_val = 0.0

    inv_ctx = {
        'inventory_mode': True,
        'inventory_name': INVENTORY_NAME,
        'force_period_date': INVENTORY_DATE,
    }

    for index, row in enumerate(rows, start=2):
        ext = str(row.get('product_id/id', '')).strip()
        loc_name = str(row.get('location_id', '')).strip()
        qty = float(row.get('inventory_quantity') or 0)
        if qty <= 0:
            continue
        try:
            product = env.ref(ext, raise_if_not_found=False)
            if not product:
                raise ValueError(f'XML-ID no encontrado: {ext}')
            pp = product.product_variant_id if product._name == 'product.template' else product

            if pp.default_code in EXCLUDED_DEFAULT_CODES or ext in EXCLUDED_XML_IDS:
                skipped += 1
                continue

            location = Location.search([
                ('complete_name', '=', loc_name),
                ('usage', '=', 'internal'),
            ], limit=1)
            if not location:
                raise ValueError(f'Ubicación no encontrada: {loc_name}')

            if pp.tracking != 'none':
                raise ValueError(f'Producto con trazabilidad {pp.tracking}: requiere lote')

            existing = Quant.search([
                ('product_id', '=', pp.id),
                ('location_id', '=', location.id),
                ('lot_id', '=', False),
                ('company_id', '=', env.company.id),
            ], limit=1)

            ctx = dict(inv_ctx)
            if existing:
                existing.with_context(ctx).write({
                    'inventory_quantity': qty,
                    'accounting_date': INVENTORY_DATE,
                })
                existing.with_context(ctx)._apply_inventory()
            else:
                quant = Quant.with_context(ctx).create({
                    'product_id': pp.id,
                    'location_id': location.id,
                    'inventory_quantity': qty,
                    'accounting_date': INVENTORY_DATE,
                })
                quant.with_context(ctx)._apply_inventory()

            total_val += qty * (pp.standard_price or 0)
            applied += 1
        except Exception as exc:
            errors.append(f'Fila {index} ({ext}): {exc}')

    env.flush_all()
    env.cr.commit()
    if skipped:
        _log(f'Filas omitidas (excluidos): {skipped}')
    _log(f'Filas aplicadas: {applied}/{len(rows)}')
    _log(f'Valor estimado (qty x costo post-ajuste): L {total_val:,.2f}')
    if errors:
        _log(f'Errores: {len(errors)}')
        for e in errors[:20]:
            _log(f'  {e}')
    return applied, errors


def verify_stock():
    _log('\n=== PASO 3: VERIFICACIÓN STOCK ===')
    loc_ids = env['stock.location'].search([
        ('complete_name', 'in', ['ESI/INSUMOS', 'ESI/Bodega MP']),
    ]).ids
    quants = env['stock.quant'].sudo().search([
        ('location_id', 'in', loc_ids),
        ('quantity', '!=', 0),
    ])
    total_qty = sum(quants.mapped('quantity'))
    _log(f'Quants con stock en INSUMOS + Bodega MP: {len(quants)}')
    _log(f'Cantidad total: {total_qty:,.2f}')

    val = 0.0
    by_loc = {}
    for q in quants:
        loc = q.location_id.complete_name
        v = q.quantity * (q.product_id.standard_price or 0)
        val += v
        by_loc.setdefault(loc, {'n': 0, 'q': 0.0, 'v': 0.0})
        by_loc[loc]['n'] += 1
        by_loc[loc]['q'] += q.quantity
        by_loc[loc]['v'] += v
    for loc in sorted(by_loc):
        d = by_loc[loc]
        _log(f'  {loc}: {d["n"]} prods | {d["q"]:,.2f} uds | L {d["v"]:,.2f}')
    _log(f'Valor total bodegas: L {val:,.2f}')


def verify_accounting():
    _log('\n=== PASO 4: VERIFICACIÓN CONTABLE ===')
    Account = env['account.account']
    moves = env['account.move'].search([
        ('date', '=', INVENTORY_DATE),
        ('ref', 'ilike', INVENTORY_NAME),
        ('state', '=', 'posted'),
    ])
    _log(f'Asientos STJ toma física: {len(moves)}')

    for code in ['11113', '11116', '11120']:
        acc = Account.search([('code', '=', code)], limit=1)
        if not acc:
            continue
        lines = env['account.move.line'].search([
            ('account_id', '=', acc.id),
            ('parent_state', '=', 'posted'),
            ('date', '=', INVENTORY_DATE),
        ])
        debit = sum(lines.mapped('debit'))
        credit = sum(lines.mapped('credit'))
        _log(f'  {code} {acc.name}: D {debit:,.2f} | C {credit:,.2f} | saldo {debit - credit:,.2f}')


update_costs()
load_inventory()
verify_stock()
verify_accounting()
_log('\n=== FIN ===')
