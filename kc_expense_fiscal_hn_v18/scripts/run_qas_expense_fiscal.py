# -*- coding: utf-8 -*-
"""QAS gastos fiscal HN — 3 empleados, anticipo y reembolso."""
import json
import traceback
from datetime import date

from odoo import Command, fields

RESULTS = []


def log(case, status, detail=''):
    RESULTS.append({'case': case, 'status': status, 'detail': detail})
    mark = 'PASS' if status == 'PASS' else 'FAIL'
    print(f'[{mark}] {case}: {detail}')


def setup_company(env):
    company = env.company
    purchase_journal = env['account.journal'].search([
        ('type', '=', 'purchase'),
        ('company_id', '=', company.id),
    ], limit=1)
    if purchase_journal:
        company.expense_journal_id = purchase_journal

    misc_journal = env['account.journal'].search([
        ('type', '=', 'general'),
        ('company_id', '=', company.id),
    ], limit=1)
    if misc_journal:
        company.kc_expense_fund_journal_id = misc_journal

    reimb = env['account.account'].search([
        ('code', '=like', '21%'),
        ('account_type', '=', 'liability_payable'),
        ('company_ids', 'in', company.id),
        ('deprecated', '=', False),
    ], limit=1)
    if reimb:
        company.kc_expense_reimbursement_account_id = reimb

    advance = env['account.account'].search([
        ('code', '=like', '11203%'),
        ('company_ids', 'in', company.id),
    ], limit=1)
    bank = env['account.journal'].search([
        ('type', 'in', ['bank', 'cash']),
        ('company_id', '=', company.id),
    ], limit=1)
    tax = env['account.tax'].search([
        ('type_tax_use', '=', 'purchase'),
        ('amount', '=', 15),
        ('company_id', '=', company.id),
    ], limit=1)
    product = env['product.product'].search([
        ('can_be_expensed', '=', True),
    ], limit=1)
    if not product:
        product = env['product.product'].create({
            'name': 'QAS Gasto Genérico',
            'type': 'service',
            'can_be_expensed': True,
            'list_price': 1000,
            'standard_price': 1000,
        })
    vendors = env['res.partner'].search([
        ('supplier_rank', '>', 0),
        ('vat', '!=', False),
    ], limit=3)
    hn = env.ref('base.hn', raise_if_not_found=False)
    return {
        'company': company,
        'purchase_journal': purchase_journal,
        'misc_journal': misc_journal,
        'reimb_account': reimb,
        'advance_account': advance,
        'bank_journal': bank,
        'tax': tax,
        'product': product,
        'vendors': vendors,
        'hn': hn,
    }


def get_employee(env, employee_id, cfg):
    employee = env['hr.employee'].browse(employee_id)
    if not employee.exists() or not employee.work_contact_id:
        raise ValueError(f'Empleado {employee_id} inválido o sin contacto')
    if cfg['reimb_account']:
        employee.work_contact_id.with_company(cfg['company']).write({
            'property_account_payable_id': cfg['reimb_account'].id,
        })
    return employee


def create_expense_sheet(env, employee, vendor, amount, cfg, advance=False,
                         doc_type='boleta', with_tax=False, doc_suffix=''):
    doc_num = f'QAS-{employee.id}-{doc_suffix or int(amount)}'
    expense_vals = {
        'name': f'QAS Gasto {employee.name} {doc_suffix}',
        'employee_id': employee.id,
        'product_id': cfg['product'].id,
        'total_amount_currency': amount,
        'payment_mode': 'own_account',
        'vendor_id': vendor.id,
        'kc_document_number': doc_num,
        'kc_document_type': doc_type,
        'kc_document_date': '2026-07-01',
        'company_id': cfg['company'].id,
        'date': '2026-07-01',
    }
    if doc_type == 'factura':
        expense_vals['kc_cai'] = 'CAI-QAS-TEST-001'
    if with_tax and cfg['tax']:
        expense_vals['tax_ids'] = [Command.set(cfg['tax'].ids)]
    sheet_vals = {
        'name': f'QAS Reporte {employee.name} {doc_suffix}',
        'employee_id': employee.id,
        'accounting_date': '2026-07-08',
        'expense_line_ids': [Command.create(expense_vals)],
    }
    if advance:
        sheet_vals['kc_advance_id'] = advance.id
    return env['hr.expense.sheet'].create(sheet_vals)


def post_sheet(sheet):
    sheet.action_submit_sheet()
    sheet.action_approve_expense_sheets()
    sheet.action_sheet_move_post()


def run_qas(env):
    env = env(user=env.ref('base.user_admin'))
    cfg = setup_company(env)
    log('SETUP', 'PASS' if cfg['purchase_journal'] and cfg['advance_account'] else 'FAIL',
        f"journal={cfg['purchase_journal'].code if cfg['purchase_journal'] else None}, "
        f"reimb={cfg['reimb_account'].code if cfg['reimb_account'] else None}, "
        f"fund_j={cfg['misc_journal'].code if cfg['misc_journal'] else None}")

    emp_a = get_employee(env, 181, cfg)   # Alberto Tejada — Reembolso
    emp_b = get_employee(env, 188, cfg)   # Estuardo Madrid — Anticipo cuadrado
    emp_c = get_employee(env, 183, cfg)   # Carlos Samuel — Sobrante + excedido

    vendor1, vendor2, vendor3 = cfg['vendors'][:3]

    # --- EMP A: Reembolso sin anticipo (2 gastos) ---
    try:
        s1 = create_expense_sheet(env, emp_a, vendor1, 3000, cfg, doc_suffix='R1')
        post_sheet(s1)
        exp = s1.expense_line_ids[0]
        bill = exp.kc_vendor_bill_id
        fund = exp.kc_fund_move_id
        ok = (
            bill and bill.partner_id == vendor1
            and bill.payment_state == 'paid'
            and fund
            and any(
                l.account_id == cfg['reimb_account'] and l.credit > 0
                for l in fund.line_ids
            )
        )
        log('QAS-A1 Reembolso boleta 3000', 'PASS' if ok else 'FAIL',
            f'bill={bill.name if bill else None}, paid={bill.payment_state if bill else None}')
    except Exception as e:
        log('QAS-A1 Reembolso boleta 3000', 'FAIL', traceback.format_exc()[-300:])

    try:
        s2 = create_expense_sheet(
            env, emp_a, vendor2, 5000, cfg,
            doc_type='factura', with_tax=True, doc_suffix='R2',
        )
        post_sheet(s2)
        exp = s2.expense_line_ids[0]
        bill = exp.kc_vendor_bill_id
        ok = bill and bill.class_document_sar == 'FA' and bill.payment_state == 'paid'
        log('QAS-A2 Reembolso factura FA+ISV 5000', 'PASS' if ok else 'FAIL',
            f'bill={bill.name if bill else None}, SAR={bill.class_document_sar if bill else None}')
    except Exception as e:
        log('QAS-A2 Reembolso factura FA+ISV 5000', 'FAIL', str(e))

    # --- EMP B: Anticipo cuadrado ---
    try:
        adv_b = env['kc.expense.advance'].create({
            'employee_id': emp_b.id,
            'amount': 8000,
            'account_advance_id': cfg['advance_account'].id,
            'journal_id': cfg['bank_journal'].id,
            'date_delivered': date(2026, 7, 8),
        })
        adv_b.action_deliver()
        s3 = create_expense_sheet(
            env, emp_b, vendor1, 4000, cfg, advance=adv_b, doc_suffix='B1',
        )
        s4 = create_expense_sheet(
            env, emp_b, vendor2, 4000, cfg, advance=adv_b, doc_suffix='B2',
        )
        post_sheet(s3)
        post_sheet(s4)
        ok = (
            abs(adv_b.amount_spent - 8000) < 0.01
            and abs(adv_b.amount_balance) < 0.01
            and all(
                e.kc_vendor_bill_id.payment_state == 'paid'
                for e in (s3.expense_line_ids | s4.expense_line_ids)
            )
        )
        wiz = env['kc.expense.advance.close.wizard'].create({
            'advance_id': adv_b.id,
            'amount_balance': adv_b.amount_balance,
        })
        wiz.action_confirm_close()
        ok = ok and adv_b.state == 'closed'
        log('QAS-B Anticipo cuadrado 8000', 'PASS' if ok else 'FAIL',
            f'gastado={adv_b.amount_spent}, saldo={adv_b.amount_balance}, estado={adv_b.state}')
    except Exception as e:
        log('QAS-B Anticipo cuadrado 8000', 'FAIL', traceback.format_exc()[-400:])

    # --- EMP C: Anticipo sobrante (entrega 10000, gasta 6000) ---
    try:
        adv_c = env['kc.expense.advance'].create({
            'employee_id': emp_c.id,
            'amount': 10000,
            'account_advance_id': cfg['advance_account'].id,
            'journal_id': cfg['bank_journal'].id,
            'date_delivered': date(2026, 7, 8),
        })
        adv_c.action_deliver()
        s5 = create_expense_sheet(
            env, emp_c, vendor3, 6000, cfg, advance=adv_c, doc_suffix='C1',
        )
        post_sheet(s5)
        ok = abs(adv_c.amount_spent - 6000) < 0.01 and adv_c.amount_balance > 0
        wiz = env['kc.expense.advance.close.wizard'].create({
            'advance_id': adv_c.id,
            'amount_balance': adv_c.amount_balance,
            'journal_id': cfg['bank_journal'].id,
        })
        wiz.action_confirm_close()
        ok = ok and adv_c.state == 'closed' and adv_c.closing_move_id
        log('QAS-C Anticipo sobrante 10000/6000', 'PASS' if ok else 'FAIL',
            f'saldo_antes_cierre={adv_c.amount_balance}, cierre={adv_c.closing_move_id.name if adv_c.closing_move_id else None}')
    except Exception as e:
        log('QAS-C Anticipo sobrante 10000/6000', 'FAIL', traceback.format_exc()[-400:])

    # --- EMP C2: Anticipo excedido (entrega 5000, gasta 7000) ---
    try:
        adv_c2 = env['kc.expense.advance'].create({
            'employee_id': emp_c.id,
            'amount': 5000,
            'account_advance_id': cfg['advance_account'].id,
            'journal_id': cfg['bank_journal'].id,
            'date_delivered': date(2026, 7, 8),
        })
        adv_c2.action_deliver()
        s6 = create_expense_sheet(
            env, emp_c, vendor1, 7000, cfg, advance=adv_c2, doc_suffix='C2',
        )
        post_sheet(s6)
        fund = s6.expense_line_ids.kc_fund_move_id
        adv_credit = sum(
            l.credit for l in fund.line_ids
            if l.account_id == cfg['advance_account']
        )
        reimb_credit = sum(
            l.credit for l in fund.line_ids
            if l.account_id == cfg['reimb_account']
        )
        ok = (
            abs(adv_credit - 5000) < 0.01
            and abs(reimb_credit - 2000) < 0.01
            and s6.expense_line_ids.kc_vendor_bill_id.payment_state == 'paid'
        )
        log('QAS-C2 Anticipo excedido 5000/7000', 'PASS' if ok else 'FAIL',
            f'anticipo_cr={adv_credit}, reembolso_cr={reimb_credit}')
    except Exception as e:
        log('QAS-C2 Anticipo excedido 5000/7000', 'FAIL', traceback.format_exc()[-400:])

    # --- Libro compras ---
    try:
        book = env['kc_fiscal_hn.book.purchases'].create({
            'date_from': date(2026, 7, 1),
            'date_to': date(2026, 7, 31),
            'company_id': cfg['company'].id,
        })
        book.action_generate()
        qas_lines = book.line_ids.filtered(
            lambda l: l.numero_factura and l.numero_factura.startswith('QAS-'),
        )
        ok = len(qas_lines) >= 5
        log('QAS-LIBRO Libro compras líneas QAS', 'PASS' if ok else 'FAIL',
            f'lineas_qas={len(qas_lines)}')
    except Exception as e:
        log('QAS-LIBRO Libro compras', 'FAIL', str(e))

    passed = sum(1 for r in RESULTS if r['status'] == 'PASS')
    print('\n=== RESUMEN QAS ===')
    print(json.dumps(RESULTS, indent=2, ensure_ascii=False))
    print(f'TOTAL: {passed}/{len(RESULTS)} PASS')
    env.cr.commit()
    return RESULTS


run_qas(env)
