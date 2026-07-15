# -*- coding: utf-8 -*-
"""Configura cuentas y diarios de gastos fiscal HN para EMSOIND."""
from odoo import SUPERUSER_ID


def _journal(env, company, code, jtype=None):
    domain = [('company_id', '=', company.id), ('code', '=', code)]
    if jtype:
        domain.append(('type', '=', jtype))
    return env['account.journal'].search(domain, limit=1)


def _account(env, company, code):
    return env['account.account'].search([
        ('code', '=like', code + '%'),
        ('company_ids', 'in', company.id),
        ('deprecated', '=', False),
    ], limit=1)


def setup_gastos_fiscal(env, company=None):
    env = env(user=SUPERUSER_ID)
    company = company or env.company
    vals = {}

    factu = _journal(env, company, 'FACTU', 'purchase')
    if not factu:
        factu = env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', company.id),
        ], limit=1)
    if factu:
        vals['expense_journal_id'] = factu.id

    misce = _journal(env, company, 'MISCE', 'general')
    if not misce:
        misce = env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', company.id),
        ], limit=1)
    if misce:
        vals['kc_expense_fund_journal_id'] = misce.id

    reimb = _account(env, company, '21101')
    if not reimb:
        reimb = env['account.account'].search([
            ('account_type', '=', 'liability_payable'),
            ('company_ids', 'in', company.id),
            ('deprecated', '=', False),
        ], limit=1)
    if reimb:
        vals['kc_expense_reimbursement_account_id'] = reimb.id

    if vals:
        company.write(vals)

    advance = _account(env, company, '11203')
    bank = _journal(env, company, 'BNK1', 'bank')
    if not bank:
        bank = env['account.journal'].search([
            ('type', 'in', ['bank', 'cash']),
            ('company_id', '=', company.id),
        ], limit=1)

    result = {
        'company': company.name,
        'expense_journal': factu.display_name if factu else None,
        'fund_journal': misce.display_name if misce else None,
        'reimbursement_account': reimb.display_name if reimb else None,
        'advance_account': advance.display_name if advance else None,
        'bank_journal': bank.display_name if bank else None,
    }
    env.cr.commit()
    return result


if __name__ == '__main__':
    import json
    print(json.dumps(setup_gastos_fiscal(env), indent=2, ensure_ascii=False))
