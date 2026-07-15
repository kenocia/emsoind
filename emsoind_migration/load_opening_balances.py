# -*- coding: utf-8 -*-
"""
Carga saldos iniciales EMSOIND — ejecutar con odoo shell.

  sudo -u odoo /opt/odoo/venv/bin/python /opt/odoo/src/community/odoo-bin shell \
    -d EMSOIND_PRUEBA --config=/etc/odoo.conf --no-http \
    < /opt/odoo/src/custom/emsoind_migration/load_opening_balances.py
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

# =============================================================================
# CONFIGURACIÓN — revisar antes de ejecutar
# =============================================================================
DRY_RUN = True  # True = solo simula; False = crea/publica asientos

BASE_DIR = Path('/opt/odoo/src/custom/emsoind_migration')
CSV_CXC = BASE_DIR / 'plantilla_cxc_apertura.csv'
CSV_CXP = BASE_DIR / 'plantilla_cxp_apertura.csv'
CSV_BALANCE = BASE_DIR / 'plantilla_balance_inicial.csv'
CSV_BANKS = BASE_DIR / 'plantilla_bancos_apertura.csv'

OPENING_DATE = '2025-12-31'  # account_opening_date - 1 día
BANK_OPENING_DATE = '2026-06-30'  # corte operativo bancos/caja (alineado con inventario)
JOURNAL_CODE = 'MISCE'
CONTRA_ACCOUNT_CODE = '999999'
DEFAULT_CXC_ACCOUNT = '11201'
DEFAULT_CXP_ACCOUNT = '21101'

# Cuentas que NO deben ir en balance_inicial.csv (se cargan por otro método)
EXCLUDED_OPENING_ACCOUNTS = {
    '11201', '11203', '11204',
    '21101', '21110', '21202',
    # Inventario ya cargado por diario STJ (30/06/2026)
    '11113', '11116', '11118', '11120',
    # Bancos/caja ya cargados por MISCE
    '11101', '11102', '11103', '11104', '11105', '11106', '11108', '11110',
}
# Reserva incobrables: asset_receivable pero va en apertura única
OPENING_RECEIVABLE_ALLOWED = frozenset({'11202'})
# Sueldos por pagar: liability_payable agregado pero saldo consolidado de apertura
OPENING_PAYABLE_ALLOWED = frozenset({'21104'})

LOAD_CXC = False
LOAD_CXP = False
LOAD_BANKS = False
LOAD_OPENING_BALANCE = False
POST_OPENING_MOVE = False
FIX_USD_BANK_ACCOUNT = True  # Asignar USD a cuenta 11104 antes de cargar BNK4
BANK_USD_RATE = 27.1183  # TC balanza: L. 65,629.53 / USD 2,420.12

# =============================================================================
# Utilidades
# =============================================================================

def _log(msg):
    print(msg, flush=True)


def _parse_date(value, default=OPENING_DATE):
    value = (value or '').strip()
    if not value:
        return default
    datetime.strptime(value, '%Y-%m-%d')
    return value


def _parse_amount(value):
    value = (value or '').strip().replace(',', '')
    if not value:
        raise ValueError('monto vacío')
    amount = float(value)
    if amount <= 0:
        raise ValueError(f'monto debe ser > 0: {amount}')
    return round(amount, 2)


def _read_csv(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(newline='', encoding='utf-8-sig') as f:
        sample = f.read(2048)
        f.seek(0)
        delimiter = ';' if sample.count(';') >= sample.count(',') else ','
        return list(csv.DictReader(f, delimiter=delimiter))


def _normalize_vat(vat):
    return (vat or '').strip().replace('-', '').replace(' ', '')


def _get_account(code):
    account = env['account.account'].with_company(env.company).search([
        ('code', '=', code),
    ], limit=1)
    if not account:
        raise ValueError(f'Cuenta no encontrada: {code}')
    return account


def _get_journal(code):
    journal = env['account.journal'].search([
        ('company_id', '=', env.company.id),
        ('code', '=', code),
    ], limit=1)
    if not journal:
        raise ValueError(f'Diario no encontrado: {code}')
    if journal.type != 'general':
        raise ValueError(
            f'El diario {code} debe ser tipo general (MISCE) para saldos de apertura '
            f'sin numeración fiscal SAR.'
        )
    return journal


def _get_partner_by_vat(vat):
    vat = _normalize_vat(vat)
    if not vat:
        raise ValueError('partner_vat vacío')
    partner = env['res.partner'].search([
        ('vat', 'ilike', vat),
        ('parent_id', '=', False),
    ], limit=1)
    if not partner:
        partner = env['res.partner'].search([
            ('vat', 'ilike', vat),
        ], limit=1)
    if not partner:
        raise ValueError(f'Contacto no encontrado con RTN: {vat}')
    return partner


def _mark_partner_rank(partner, rank_field):
    if DRY_RUN:
        return
    if rank_field == 'customer' and not partner.customer_rank:
        partner.customer_rank = 1
    if rank_field == 'supplier' and not partner.supplier_rank:
        partner.supplier_rank = 1


def _existing_opening_ref(ref, move_type='entry'):
    return env['account.move'].search([
        ('company_id', '=', env.company.id),
        ('ref', '=', ref),
        ('move_type', '=', move_type),
        ('state', '!=', 'cancel'),
    ], limit=1)


# =============================================================================
# Carga CxC / CxP — un asiento misceláneo por documento
# =============================================================================

def _load_ar_ap_rows(rows, *, kind):
    """
    kind: 'cxc' -> débito en cuenta por cobrar
          'cxp' -> crédito en cuenta por pagar
    """
    journal = _get_journal(JOURNAL_CODE)
    contra = _get_account(CONTRA_ACCOUNT_CODE)
    default_account = DEFAULT_CXC_ACCOUNT if kind == 'cxc' else DEFAULT_CXP_ACCOUNT
    rank_field = 'customer' if kind == 'cxc' else 'supplier'
    prefix = 'OPEN-CXC' if kind == 'cxc' else 'OPEN-CXP'

    created = 0
    skipped = 0
    total = 0.0
    errors = []

    for i, row in enumerate(rows, start=2):
        try:
            ref = (row.get('ref') or '').strip()
            if not ref:
                raise ValueError('ref obligatorio')

            if ref.startswith('OPEN-CXP-') or ref.startswith('OPEN-CXC-'):
                ref_key = ref
            else:
                ref_key = f'{prefix}-{ref}'

            if _existing_opening_ref(ref_key):
                _log(f'  [SKIP] {ref_key} ya existe')
                skipped += 1
                continue

            partner = _get_partner_by_vat(row.get('partner_vat'))
            account = _get_account((row.get('cuenta') or default_account).strip())
            amount = _parse_amount(row.get('monto'))
            date = _parse_date(row.get('fecha'))
            due_date = _parse_date(row.get('fecha_vencimiento'), default='') if row.get('fecha_vencimiento') else False
            notes = (row.get('notas') or f'Saldo inicial {kind.upper()} {ref}').strip()

            if account.account_type != ('asset_receivable' if kind == 'cxc' else 'liability_payable'):
                raise ValueError(f'Cuenta {account.code} no es del tipo esperado para {kind.upper()}')

            line_recv = {
                'name': notes,
                'partner_id': partner.id,
                'account_id': account.id,
                'debit': amount if kind == 'cxc' else 0.0,
                'credit': amount if kind == 'cxp' else 0.0,
            }
            if due_date:
                line_recv['date_maturity'] = due_date

            line_contra = {
                'name': 'Contrapartida apertura',
                'account_id': contra.id,
                'debit': amount if kind == 'cxp' else 0.0,
                'credit': amount if kind == 'cxc' else 0.0,
            }

            vals = {
                'move_type': 'entry',
                'journal_id': journal.id,
                'date': date,
                'ref': ref_key,
                'narration': f'Documento legado: {ref}',
                'line_ids': [(0, 0, line_recv), (0, 0, line_contra)],
            }

            _log(
                f'  [{"DRY" if DRY_RUN else "OK"}] {ref_key} | {partner.display_name[:40]} | '
                f'{account.code} | L. {amount:,.2f}'
            )

            if not DRY_RUN:
                move = env['account.move'].with_context(skip_account_deprecation_check=True).create(vals)
                move.action_post()
                _mark_partner_rank(partner, rank_field)

            created += 1
            total += amount

        except Exception as exc:
            errors.append(f'Fila {i} ({row.get("ref", "?")}): {exc}')

    return {
        'kind': kind,
        'created': created,
        'skipped': skipped,
        'total': total,
        'errors': errors,
    }


def load_cxc():
    _log('\n=== CARGA CxC ===')
    rows = [r for r in _read_csv(CSV_CXC) if (r.get('partner_vat') or '').strip()]
    return _load_ar_ap_rows(rows, kind='cxc')


def load_cxp():
    _log('\n=== CARGA CxP ===')
    rows = [r for r in _read_csv(CSV_CXP) if (r.get('partner_vat') or '').strip()]
    return _load_ar_ap_rows(rows, kind='cxp')


# =============================================================================
# Bancos y caja — MISCE vs cuenta tránsito (11110 / 11108)
# =============================================================================

def _get_bank_journal(code):
    journal = env['account.journal'].search([
        ('company_id', '=', env.company.id),
        ('code', '=', code),
    ], limit=1)
    if not journal:
        raise ValueError(f'Diario bancario no encontrado: {code}')
    if journal.type not in ('bank', 'cash'):
        raise ValueError(f'El diario {code} debe ser tipo banco o caja, no {journal.type}')
    return journal


def _ensure_usd_bank_account(code='11104'):
    usd = env.ref('base.USD', raise_if_not_found=False)
    if not usd:
        raise ValueError('Moneda USD no encontrada en el sistema')
    account = _get_account(code)
    if account.currency_id == usd:
        _log(f'  Cuenta {code} ya tiene moneda USD')
        return account
    _log(f'  [{"DRY" if DRY_RUN else "OK"}] Asignar USD a cuenta {code} ({account.name})')
    if not DRY_RUN:
        account.currency_id = usd.id
    return account


def _ensure_usd_exchange_rate(date, rate):
    usd = env.ref('base.USD')
    company = env.company
    existing = env['res.currency.rate'].search([
        ('currency_id', '=', usd.id),
        ('name', '=', date),
        ('company_id', 'in', [company.id, company.root_id.id, False]),
    ], limit=1)
    if existing:
        current = env['res.currency']._get_conversion_rate(usd, company.currency_id, company, date)
        if company.currency_id.is_zero(current - rate):
            _log(f'  TC USD al {date} ya es {rate:.4f}')
            return
        _log(f'  [{"DRY" if DRY_RUN else "OK"}] Actualizar TC USD {date}: {current:.4f} → {rate:.4f}')
        if not DRY_RUN:
            existing.write({'inverse_company_rate': rate})
        return
    _log(f'  [{"DRY" if DRY_RUN else "OK"}] Crear TC USD {date}: {rate:.4f} LPS/USD')
    if not DRY_RUN:
        env['res.currency.rate'].create({
            'currency_id': usd.id,
            'name': date,
            'inverse_company_rate': rate,
            'company_id': company.root_id.id,
        })


def _company_amount_from_foreign(amount, currency, date):
    company = env.company
    if currency == company.currency_id:
        return round(amount, 2)
    return round(
        currency._convert(amount, company.currency_id, company, date),
        2,
    )


def _bank_opening_ref(journal_code, date):
    return f'OPEN-BNK-{journal_code}-{date}'


def load_banks():
    _log('\n=== CARGA BANCOS Y CAJA (vs tránsito) ===')
    journal = _get_journal(JOURNAL_CODE)
    rows = [r for r in _read_csv(CSV_BANKS) if (r.get('diario') or '').strip()]
    company = env.company

    if FIX_USD_BANK_ACCOUNT:
        _ensure_usd_bank_account('11104')

    has_usd = any((r.get('diario') or '').strip() == 'BNK4' for r in rows)
    bank_date = BANK_OPENING_DATE
    for r in rows:
        if (r.get('saldo_inicial') or '').strip():
            bank_date = _parse_date(r.get('fecha'), default=BANK_OPENING_DATE)
            break
    if has_usd and BANK_USD_RATE:
        _ensure_usd_exchange_rate(bank_date, BANK_USD_RATE)

    created = 0
    skipped = 0
    total_hnl = 0.0
    errors = []

    for i, row in enumerate(rows, start=2):
        journal_code = (row.get('diario') or '').strip()
        try:
            bank_code = (row.get('cuenta_banco') or '').strip()
            transit_code = (row.get('cuenta_transito') or '').strip()
            if not bank_code or not transit_code:
                raise ValueError('cuenta_banco y cuenta_transito son obligatorios')

            amount = _parse_amount(row.get('saldo_inicial'))
            date = _parse_date(row.get('fecha'), default=BANK_OPENING_DATE)
            notes = (row.get('notas') or f'Saldo inicial {journal_code}').strip()
            ref = _bank_opening_ref(journal_code, date)

            if _existing_opening_ref(ref):
                _log(f'  [SKIP] {ref} ya existe')
                skipped += 1
                continue

            bank_journal = _get_bank_journal(journal_code)
            bank_account = _get_account(bank_code)
            transit_account = _get_account(transit_code)

            line_currency = bank_journal.currency_id or bank_account.currency_id or company.currency_id
            amount_currency = amount
            debit_company = _company_amount_from_foreign(amount_currency, line_currency, date)

            line_bank = {
                'name': notes,
                'account_id': bank_account.id,
                'debit': debit_company,
                'credit': 0.0,
            }
            if line_currency != company.currency_id:
                line_bank['currency_id'] = line_currency.id
                line_bank['amount_currency'] = amount_currency

            line_transit = {
                'name': f'Tránsito apertura {journal_code}',
                'account_id': transit_account.id,
                'debit': 0.0,
                'credit': debit_company,
            }

            vals = {
                'move_type': 'entry',
                'journal_id': journal.id,
                'date': date,
                'ref': ref,
                'narration': notes,
                'line_ids': [(0, 0, line_bank), (0, 0, line_transit)],
            }

            curr_label = line_currency.name
            _log(
                f'  [{"DRY" if DRY_RUN else "OK"}] {ref} | {bank_account.code} | '
                f'{amount_currency:,.2f} {curr_label} (≈ L. {debit_company:,.2f})'
            )

            if not DRY_RUN:
                move = env['account.move'].with_context(skip_account_deprecation_check=True).create(vals)
                move.action_post()

            created += 1
            total_hnl += debit_company

        except Exception as exc:
            errors.append(f'Fila {i} ({journal_code or "?"}): {exc}')

    return {
        'created': created,
        'skipped': skipped,
        'total': total_hnl,
        'errors': errors,
    }


# =============================================================================
# Balance inicial — resto de cuentas (plan contable)
# =============================================================================

def load_opening_balance_accounts():
    _log('\n=== BALANCE INICIAL (plan de cuentas) ===')
    company = env.company
    rows = [r for r in _read_csv(CSV_BALANCE) if (r.get('cuenta') or '').strip()]

    updated = 0
    skipped = 0
    errors = []

    if company.opening_move_posted() and not DRY_RUN:
        raise UserError(
            'El asiento de apertura ya está publicado. '
            'Pásalo a borrador antes de modificar saldos iniciales.'
        )

    for i, row in enumerate(rows, start=2):
        code = (row.get('cuenta') or '').strip()
        try:
            if code in EXCLUDED_OPENING_ACCOUNTS:
                raise ValueError(
                    f'Cuenta {code} excluida: debe cargarse en plantilla CxC/CxP, no aquí.'
                )

            raw_balance = (row.get('saldo_inicial') or '').strip().replace(',', '')
            if not raw_balance:
                continue
            balance = round(float(raw_balance), 2)
            if company.currency_id.is_zero(balance):
                skipped += 1
                continue

            account = _get_account(code)
            if (
                account.account_type in ('asset_receivable', 'liability_payable')
                and code not in OPENING_RECEIVABLE_ALLOWED
                and code not in OPENING_PAYABLE_ALLOWED
            ):
                raise ValueError(
                    f'Cuenta {code} es CxC/CxP: usar plantilla de documentos, no balance inicial.'
                )

            _log(f'  [{"DRY" if DRY_RUN else "OK"}] {code} | saldo_inicial = {balance:,.2f}')

            if not DRY_RUN:
                account.opening_balance = balance

            updated += 1

        except Exception as exc:
            errors.append(f'Fila {i} ({code or "?"}): {exc}')

    if not DRY_RUN and updated:
        env.flush_all()

    # Validar cuadre esperado con CxC/CxP ya cargados
    if updated:
        positive = negative = 0.0
        for row in rows:
            code = (row.get('cuenta') or '').strip()
            raw = (row.get('saldo_inicial') or '').strip().replace(',', '')
            if not code or not raw:
                continue
            bal = round(float(raw), 2)
            if bal > 0:
                positive += bal
            elif bal < 0:
                negative += abs(bal)
        net = round(positive - negative, 2)
        contra = env['account.move.line'].search([
            ('account_id.code', '=', CONTRA_ACCOUNT_CODE),
            ('parent_state', '=', 'posted'),
            ('ref', 'ilike', 'OPEN-CX%'),
        ])
        contra_net = round(sum(contra.mapped('balance')), 2)
        _log(f'  Cuadre CSV: activos L. {positive:,.2f} | pasivo+patrimonio L. {negative:,.2f} | neto L. {net:,.2f}')
        _log(f'  Saldo 999999 por CxC/CxP: L. {contra_net:,.2f}')
        if company.currency_id.is_zero(net + contra_net):
            _log('  ✓ CSV cuadra con 999999 (al publicar apertura debe quedar en cero)')
        else:
            _log(
                f'  ⚠ Diferencia L. {net + contra_net:,.2f}. Ajuste saldos hasta que '
                f'activos − pasivo/patrimonio = {abs(contra_net):,.2f}'
            )

    opening_move = company.account_opening_move_id
    if not DRY_RUN and updated:
        env.cr.precommit.run()
        opening_move = company.account_opening_move_id
        if opening_move:
            _log(f'  Asiento apertura generado: {opening_move.name} | líneas: {len(opening_move.line_ids)}')
            _log(f'  Débitos L. {sum(opening_move.line_ids.mapped("debit")):,.2f} | '
                 f'Créditos L. {sum(opening_move.line_ids.mapped("credit")):,.2f}')
    if not DRY_RUN and POST_OPENING_MOVE and opening_move and opening_move.state == 'draft':
        opening_move.with_context(skip_account_deprecation_check=True).action_post()
        _log(f'  Asiento de apertura publicado: {opening_move.name}')

    return {
        'updated': updated,
        'skipped': skipped,
        'errors': errors,
        'opening_move': opening_move.name if opening_move else None,
        'opening_state': opening_move.state if opening_move else None,
    }


# =============================================================================
# Validación de cuadre
# =============================================================================

def validate_totals():
    _log('\n=== VALIDACIÓN ===')
    company = env.company
    contra = _get_account(CONTRA_ACCOUNT_CODE)

    open_moves = env['account.move'].search([
        ('company_id', '=', company.id),
        ('ref', 'ilike', 'OPEN-CX%'),
        ('state', '=', 'posted'),
    ])
    cxc_total = sum(
        l.debit - l.credit
        for m in open_moves.filtered(lambda x: x.ref.startswith('OPEN-CXC'))
        for l in m.line_ids
        if l.account_id.account_type == 'asset_receivable'
    )
    cxp_total = sum(
        l.credit - l.debit
        for m in open_moves.filtered(lambda x: x.ref.startswith('OPEN-CXP'))
        for l in m.line_ids
        if l.account_id.account_type == 'liability_payable'
    )

    _log(f'  Documentos OPEN-CXC publicados: {len(open_moves.filtered(lambda x: x.ref.startswith("OPEN-CXC")))}')
    _log(f'  Documentos OPEN-CXP publicados: {len(open_moves.filtered(lambda x: x.ref.startswith("OPEN-CXP")))}')
    _log(f'  Total CxC cargado (1120x): L. {cxc_total:,.2f}')
    _log(f'  Total CxP cargado (2110x/2120x): L. {cxp_total:,.2f}')

    om = company.account_opening_move_id
    if om:
        _log(f'  Asiento apertura: {om.name} | estado: {om.state}')
        total_debit = sum(om.line_ids.mapped('debit'))
        total_credit = sum(om.line_ids.mapped('credit'))
        _log(f'  Apertura débitos: L. {total_debit:,.2f} | créditos: L. {total_credit:,.2f}')
        diff = round(total_debit - total_credit, 2)
        if diff:
            _log(f'  ⚠ Apertura DESCUADRADA por L. {diff:,.2f}')
        else:
            _log('  ✓ Asiento de apertura cuadrado')

    contra_lines = env['account.move.line'].search([
        ('account_id', '=', contra.id),
        ('parent_state', '=', 'posted'),
        ('date', '<=', OPENING_DATE),
    ])
    contra_net = sum(contra_lines.mapped('balance'))
    _log(f'  Saldo neto {CONTRA_ACCOUNT_CODE} al corte: L. {contra_net:,.2f}')
    if company.currency_id.is_zero(contra_net):
        _log('  ✓ Cuenta puente 999999 en cero (cuadre global OK)')
    else:
        _log(
            f'  ⚠ {CONTRA_ACCOUNT_CODE} no está en cero. Revise que balance_inicial.csv '
            f'cuadre con CxC/CxP del sistema legado.'
        )

    bank_codes = ['11101', '11102', '11103', '11104', '11105', '11106', '11108', '11110']
    _log('  Saldos bancos/caja y tránsito:')
    for code in bank_codes:
        account = env['account.account'].search([('code', '=', code)], limit=1)
        if not account:
            continue
        lines = env['account.move.line'].search([
            ('account_id', '=', account.id),
            ('parent_state', '=', 'posted'),
        ])
        balance = round(sum(lines.mapped('debit')) - sum(lines.mapped('credit')), 2)
        if not company.currency_id.is_zero(balance):
            curr = f' ({account.currency_id.name})' if account.currency_id else ''
            _log(f'    {code}: L. {balance:,.2f}{curr}')


# =============================================================================
# Main
# =============================================================================

from odoo.exceptions import UserError

_log('=' * 72)
_log(f'EMSOIND — Carga saldos iniciales | empresa: {env.company.name}')
_log(f'Modo: {"SIMULACIÓN (DRY_RUN)" if DRY_RUN else "*** EJECUCIÓN REAL ***"}')
_log(f'Fecha documentos: {OPENING_DATE} | Diario: {JOURNAL_CODE}')
_log('=' * 72)

results = {}

if LOAD_CXC:
    results['cxc'] = load_cxc()
if LOAD_CXP:
    results['cxp'] = load_cxp()
if LOAD_BANKS:
    results['banks'] = load_banks()
if LOAD_OPENING_BALANCE:
    results['opening'] = load_opening_balance_accounts()

_log('\n=== RESUMEN ===')
for key, res in results.items():
    if not res:
        continue
    if 'created' in res:
        _log(
            f'  {key.upper()}: {res["created"]} creados, {res["skipped"]} omitidos, '
            f'total L. {res["total"]:,.2f}, errores: {len(res["errors"])}'
        )
    elif 'updated' in res:
        _log(
            f'  {key.upper()}: {res["updated"]} cuentas, {res["skipped"]} omitidas, '
            f'errores: {len(res["errors"])} | apertura: {res["opening_move"]} ({res["opening_state"]})'
        )
    for err in res.get('errors', []):
        _log(f'    ERROR: {err}')

if not DRY_RUN:
    validate_totals()
    env.cr.commit()
    _log('  ✓ Cambios confirmados en base de datos (commit)')
else:
    _log('\n  Simulación terminada. Revise filas arriba y luego ponga DRY_RUN = False.')

_log('\nFin.')
