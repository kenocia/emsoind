# -*- coding: utf-8 -*-
"""Configuración de prueba — Guías de Remisión SAR en EMSOIND_PRUEBA.

Ejecutar:
    sudo -u odoo /opt/odoo/venv/bin/python3 /opt/odoo/src/community/odoo-bin shell \\
        --config /etc/odoo.conf -d EMSOIND_PRUEBA --no-http \\
        < /opt/odoo/src/custom/kc_fiscal_hn_v18/scripts/setup_guias_remision_emsoind.py
"""
from datetime import date

DRY_RUN = False
MARKER = 'GRTEST'

company = env.company
Sequence = env['ir.sequence']
DateRange = env['ir.sequence.date_range']
PickingType = env['stock.picking.type']

print('=' * 72)
print(f'GUÍAS DE REMISIÓN — {"DRY-RUN" if DRY_RUN else "APLICAR"} — BD: {env.cr.dbname}')
print(f'Empresa: {company.name} (id={company.id})')
print('=' * 72)

# ── 1. Normalizar códigos XML con espacios/saltos de línea ───────────────
guide_candidates = Sequence.search([
    ('is_fiscal', '=', True),
    ('code', 'ilike', 'stock.picking.guide'),
    ('company_id', 'in', [company.id, False]),
])
for seq in guide_candidates:
    clean_code = (seq.code or '').strip()
    clean_name = (seq.name or '').strip()
    if seq.code != clean_code or seq.name != clean_name:
        print(f'Normalizando seq id={seq.id}: code {repr(seq.code)} → {repr(clean_code)}')
        if not DRY_RUN:
            seq.write({'code': clean_code, 'name': clean_name or 'Secuencia Fiscal Guías de Remisión'})

guide_seq = Sequence.search([
    ('is_fiscal', '=', True),
    ('code', '=', 'stock.picking.guide'),
    ('company_id', '=', company.id),
], limit=1)

if not guide_seq:
    print('\n⚠️  No existe secuencia GR; se creará una de prueba.')
    vals_seq = {
        'name': 'Secuencia Fiscal Guías de Remisión',
        'code': 'stock.picking.guide',
        'prefix': 'GR/%(range_year)s/',
        'padding': 8,
        'implementation': 'no_gap',
        'use_date_range': True,
        'is_fiscal': True,
        'fiscal_type': 'other',
        'default_dias_alerta': 30,
        'default_numeros_alerta': 50,
        'auto_alert': True,
        'active': True,
        'company_id': company.id,
    }
    if not DRY_RUN:
        guide_seq = Sequence.create(vals_seq)
else:
    print(f'\nSecuencia GR encontrada: id={guide_seq.id} prefix={guide_seq.prefix!r}')

# ── 2. Rango CAI de prueba (solo si no hay rango activo) ─────────────────
year_start = date(2026, 1, 1)
year_end = date(2026, 12, 31)
test_cai = f'{MARKER}-AAAAAA-BBBBBB-CCCCCC-DDDDDD-01'

active_range = DateRange.search([
    ('sequence_id', '=', guide_seq.id),
    ('date_from', '<=', date.today()),
    ('date_to', '>=', date.today()),
    ('cai', '!=', False),
], limit=1)

if active_range:
    print(f'Rango CAI activo existente: id={active_range.id} CAI={active_range.cai}')
else:
    existing = DateRange.search([
        ('sequence_id', '=', guide_seq.id),
        ('cai', '=', test_cai),
    ], limit=1)
    vals_range = {
        'sequence_id': guide_seq.id,
        'date_from': year_start,
        'date_to': year_end,
        'cai': test_cai,
        'rangoInicial': 1,
        'rangoFinal': 300,
        'number_next': 1,
        'number_next_actual': 1,
        'dias_alerta': 30,
        'numeros_alerta': 50,
    }
    if existing:
        print(f'Actualizando rango CAI id={existing.id}')
        if not DRY_RUN:
            existing.write(vals_range)
        active_range = existing
    else:
        print('Creando rango CAI de prueba 2026 (1-300)...')
        if not DRY_RUN:
            active_range = DateRange.create(vals_range)

# ── 3. Vincular secuencia SAR a tipos de operación salida ────────────────
out_types = PickingType.search([
    ('code', '=', 'outgoing'),
    ('warehouse_id.company_id', '=', company.id),
])
linked = 0
for pt in out_types:
    if pt.sequence_sar_id == guide_seq:
        print(f'  [OK] {pt.display_name}')
        continue
    print(f'  [ASIGNAR] {pt.display_name} → seq {guide_seq.id}')
    if not DRY_RUN:
        pt.write({'sequence_sar_id': guide_seq.id})
    linked += 1

if not DRY_RUN:
    env.cr.commit()

# ── 4. Resumen ───────────────────────────────────────────────────────────
guide_seq = Sequence.browse(guide_seq.id)
active_range = DateRange.search([
    ('sequence_id', '=', guide_seq.id),
    ('date_from', '<=', date.today()),
    ('date_to', '>=', date.today()),
], limit=1)

print('\n' + '=' * 72)
print('RESUMEN')
print('=' * 72)
print(f'Secuencia: id={guide_seq.id} code={guide_seq.code!r} prefix={guide_seq.prefix!r}')
if active_range:
    print(
        f'CAI vigente: {active_range.cai} | {active_range.date_from}..{active_range.date_to} | '
        f'corr {active_range.rangoInicial}-{active_range.rangoFinal} | next={active_range.number_next_actual}'
    )
else:
    print('⚠️  Sin rango CAI activo para hoy')

for pt in out_types:
    sar = pt.sequence_sar_id
    status = 'OK' if sar == guide_seq else 'PENDIENTE'
    print(f'  [{status}] {pt.display_name} → {sar.id if sar else "sin secuencia"}')

print('\nFlujo de prueba en UI:')
print('  Inventario → Entregas → [salida] → pestaña SAR')
print('  → Motivo traslado + transportista → "Actualizar Numeración SAR"')
print('  → Validar → Imprimir "Guía Remisión"')
print('=' * 72)
