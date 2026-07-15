# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from datetime import timedelta

from odoo import api, fields, models


class KenociaTreasuryDashboard(models.AbstractModel):
    _name = 'kenocia.treasury.dashboard'
    _description = 'Dashboard Tesorería Kenocia'

    @api.model
    def get_dashboard_data(self, filters=None):
        """Único punto de entrada para todos los datos del dashboard."""
        self.check_access('read')
        if not filters:
            filters = {}

        if filters.get('company_ids'):
            companies = self.env['res.company'].browse(filters['company_ids'])
        else:
            companies = self.env.companies

        company_ids = companies.ids
        today = fields.Date.today()
        date_from = self._coerce_filter_date(
            filters.get('date_from'), today.replace(day=1),
        )
        date_to = self._coerce_filter_date(filters.get('date_to'), today)

        journal_ids = filters.get('journal_ids')
        journal_ctx = self._parse_journal_filter(company_ids, journal_ids)

        banks = self._get_bank_balances(company_ids, journal_ctx)
        cash_journals = self._get_cash_journal_balances(company_ids, journal_ctx)
        petty_cash = self._get_petty_cash_data(
            company_ids,
            filters.get('petty_fund_ids'),
            journal_ctx,
        )
        liquidity_journals = self._build_liquidity_journals(
            banks, cash_journals, petty_cash,
        )

        return {
            'banks': banks,
            'cash_journals': cash_journals,
            'cash_total': round(sum(item['balance'] for item in cash_journals), 2),
            'liquidity_journals': liquidity_journals,
            'petty_cash': petty_cash,
            'filter_context': {
                'journal_type': journal_ctx['type'],
                'journal_ids': journal_ids or [],
            },
            'cxc': self._get_cxc_data(company_ids, today),
            'cxp': self._get_cxp_data(company_ids, today),
            'cash_flow': self._get_cash_flow_projection(company_ids, today),
            'alerts': self._get_alerts(company_ids, today),
            'filters_meta': self._get_filters_meta(company_ids),
            'period': {
                'date_from': fields.Date.to_string(date_from),
                'date_to': fields.Date.to_string(date_to),
            },
        }

    @api.model
    def _coerce_filter_date(self, value, default):
        """Convierte fechas ISO del frontend (str) a date de Odoo."""
        if not value:
            return default
        if isinstance(value, str):
            return fields.Date.from_string(value)
        return value

    def _accounting_env(self, company_ids):
        """Entorno elevado para KPIs contables (solo lectura agregada).

        Usuarios de tesorería (p. ej. custodio) no tienen grupo Accounting,
        pero necesitan ver saldos y aging en el dashboard operativo.
        """
        return self.sudo().with_context(allowed_company_ids=company_ids).env

    def _parse_journal_filter(self, company_ids, journal_ids):
        """Interpreta filtro de diarios separando banco vs efectivo."""
        if not journal_ids:
            return {
                'type': 'all',
                'bank_ids': None,
                'cash_ids': None,
            }

        journals = self._accounting_env(company_ids)['account.journal'].browse(
            journal_ids,
        )
        bank_ids = journals.filtered(lambda journal: journal.type == 'bank').ids
        cash_ids = journals.filtered(lambda journal: journal.type == 'cash').ids

        if bank_ids and not cash_ids:
            filter_type = 'bank'
        elif cash_ids and not bank_ids:
            filter_type = 'cash'
        else:
            filter_type = 'mixed'

        return {
            'type': filter_type,
            'bank_ids': bank_ids,
            'cash_ids': cash_ids,
        }

    def _journal_ids_for_type(self, journal_ctx, journal_type):
        """IDs de diario a filtrar; None = sin filtro, [] = excluir todo."""
        if journal_ctx['type'] == 'all':
            return None
        key = 'bank_ids' if journal_type == 'bank' else 'cash_ids'
        return journal_ctx.get(key) or []

    def _get_journal_liquidity_accounts(self, journal):
        """Cuentas de liquidez del diario (default + métodos de pago)."""
        accounts = journal.default_account_id
        if journal.type in ('bank', 'cash', 'credit'):
            accounts |= journal._get_journal_inbound_outstanding_payment_accounts()
            accounts |= journal._get_journal_outbound_outstanding_payment_accounts()
        if journal.type == 'cash' and journal.default_account_id:
            self.env.cr.execute("""
                SELECT DISTINCT aml.account_id
                  FROM account_move_line aml
                  JOIN account_account aa ON aa.id = aml.account_id
                 WHERE aml.journal_id = %s
                   AND aml.payment_id IS NOT NULL
                   AND aml.account_id != %s
                   AND aa.account_type IN ('asset_cash', 'asset_current')
            """, (journal.id, journal.default_account_id.id))
            accounts |= self.env['account.account'].browse(
                row[0] for row in self.env.cr.fetchall()
            )
        return accounts.filtered(lambda account: account)

    def _compute_journal_balance(self, journal):
        """Saldo posted del diario en sus cuentas de liquidez."""
        accounts = self._get_journal_liquidity_accounts(journal)
        if not accounts:
            return 0.0

        self.env.cr.execute("""
            SELECT COALESCE(SUM(aml.balance), 0.0)
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            WHERE aml.account_id IN %s
              AND aml.journal_id = %s
              AND am.state = 'posted'
              AND aml.company_id = %s
              AND aml.display_type NOT IN (
                  'line_section', 'line_note'
              )
        """, (tuple(accounts.ids), journal.id, journal.company_id.id))

        result = self.env.cr.fetchone()
        return float(result[0]) if result else 0.0

    def _get_bank_balances(self, company_ids, journal_ctx=None):
        """Saldo contable real de diarios bancarios (type=bank)."""
        journal_ctx = journal_ctx or {'type': 'all', 'bank_ids': None}
        domain = [
            ('type', '=', 'bank'),
            ('company_id', 'in', company_ids),
        ]
        bank_ids = self._journal_ids_for_type(journal_ctx, 'bank')
        if bank_ids is not None:
            domain.append(('id', 'in', bank_ids or [0]))

        journals = self._accounting_env(company_ids)['account.journal'].search(domain)
        banks = []
        total = 0.0

        for journal in journals:
            balance = self._compute_journal_balance(journal)
            banks.append({
                'id': journal.id,
                'name': journal.name,
                'balance': round(balance, 2),
                'type': journal.type,
                'company': journal.company_id.name,
            })
            total += balance

        return {
            'journals': sorted(banks, key=lambda item: -item['balance']),
            'total': round(total, 2),
            'count': len(banks),
        }

    def _get_cash_journal_balances(self, company_ids, journal_ctx=None):
        """Saldos de diarios cash (efectivo operativo Odoo)."""
        journal_ctx = journal_ctx or {'type': 'all', 'cash_ids': None}
        domain = [
            ('type', '=', 'cash'),
            ('company_id', 'in', company_ids),
        ]
        cash_ids = self._journal_ids_for_type(journal_ctx, 'cash')
        if cash_ids is not None:
            domain.append(('id', 'in', cash_ids or [0]))

        journals = self._accounting_env(company_ids)['account.journal'].search(domain)
        return [
            {
                'id': journal.id,
                'name': journal.name,
                'balance': round(self._compute_journal_balance(journal), 2),
                'company': journal.company_id.name,
            }
            for journal in journals
        ]

    def _build_liquidity_journals(self, banks, cash_journals, petty_cash):
        """Lista unificada bancos + efectivo para la gráfica de saldos."""
        funds_by_journal = {
            fund['journal_id']: fund
            for fund in petty_cash['funds']
            if fund.get('journal_id')
        }
        items = []

        for journal in banks['journals']:
            items.append({
                'id': f"bank-{journal['id']}",
                'name': journal['name'],
                'balance': journal['balance'],
                'kind': 'bank',
                'company': journal.get('company', ''),
            })

        for journal in cash_journals:
            fund = funds_by_journal.get(journal['id'])
            display_name = journal['name']
            if fund:
                display_name = f"{journal['name']} — {fund['name']}"
            items.append({
                'id': f"cash-{journal['id']}",
                'name': display_name,
                'balance': journal['balance'],
                'kind': 'cash',
                'company': journal.get('company', ''),
                'fund_name': fund['name'] if fund else '',
            })

        total = round(sum(item['balance'] for item in items), 2)
        return {
            'journals': items,
            'total': total,
            'count': len(items),
        }

    def _get_petty_cash_data(self, company_ids, petty_fund_ids=None, journal_ctx=None):
        """Fondos Kenocia: saldo operativo + saldo contable del diario cash."""
        journal_ctx = journal_ctx or {'type': 'all', 'cash_ids': None}
        domain = [('company_id', 'in', company_ids)]
        if petty_fund_ids:
            domain.append(('id', 'in', petty_fund_ids))
        else:
            domain.append(('state', '=', 'open'))

        cash_ids = self._journal_ids_for_type(journal_ctx, 'cash')
        if cash_ids is not None and cash_ids:
            domain.append(('journal_id', 'in', cash_ids))

        funds = self.env['kenocia.petty.cash'].search(domain)
        result = []
        total_operational = 0.0
        total_accounting = 0.0

        for fund in funds:
            pct = round(
                fund.amount_available / fund.amount_authorized * 100, 1,
            ) if fund.amount_authorized else 0
            journal = fund.journal_id.sudo() if fund.journal_id else False
            accounting_balance = (
                self._compute_journal_balance(journal) if journal else 0.0
            )
            pending_lines = fund.line_ids.filtered(
                lambda line: line.state == 'delivered',
            )

            result.append({
                'id': fund.id,
                'name': fund.name,
                'available': round(fund.amount_available, 2),
                'authorized': round(fund.amount_authorized, 2),
                'recharge_total': round(fund.recharge_total, 2),
                'pending': round(fund.amount_pending, 2),
                'pct': pct,
                'accounting_balance': round(accounting_balance, 2),
                'journal_id': fund.journal_id.id if fund.journal_id else False,
                'journal_name': fund.journal_id.name if fund.journal_id else '',
                'pending_advances': len(pending_lines),
                'custodian': fund.custodian_id.name or '',
                'company': fund.company_id.name,
            })
            total_operational += fund.amount_available
            total_accounting += accounting_balance

        return {
            'funds': result,
            'total_available': round(total_accounting, 2),
            'total_operational': round(total_operational, 2),
            'total_authorized': round(sum(fund.amount_authorized for fund in funds), 2),
            'open_count': len(funds),
            'pending_advances': sum(item['pending_advances'] for item in result),
        }

    def _get_cxc_data(self, company_ids, today):
        invoices = self._accounting_env(company_ids)['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('company_id', 'in', company_ids),
        ])
        total = current = warning = critical = 0.0
        cnt = cnt_c = cnt_w = cnt_k = 0
        top = []

        for inv in invoices:
            due = inv.invoice_date_due or today
            days = (today - due).days
            amt = inv.amount_residual
            total += amt
            cnt += 1
            top.append({
                'partner': inv.partner_id.name,
                'amount': amt,
                'days': days,
            })
            if days <= 0:
                current += amt
                cnt_c += 1
            elif days <= 60:
                warning += amt
                cnt_w += 1
            else:
                critical += amt
                cnt_k += 1

        top_sorted = sorted(top, key=lambda item: -item['days'])[:5]

        return {
            'total': round(total, 2),
            'count': cnt,
            'current': round(current, 2),
            'count_current': cnt_c,
            'warning': round(warning, 2),
            'count_warning': cnt_w,
            'critical': round(critical, 2),
            'count_critical': cnt_k,
            'top': top_sorted,
        }

    def _get_cxp_data(self, company_ids, today):
        bills = self._accounting_env(company_ids)['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('company_id', 'in', company_ids),
        ])
        total = current = due_week = overdue = 0.0
        cnt = cnt_c = cnt_w = cnt_o = 0
        top = []

        for bill in bills:
            due = bill.invoice_date_due or today
            days = (today - due).days
            amt = bill.amount_residual
            total += amt
            cnt += 1
            top.append({
                'partner': bill.partner_id.name,
                'amount': amt,
                'days': days,
            })
            if days < 0:
                current += amt
                cnt_c += 1
            elif days <= 7:
                due_week += amt
                cnt_w += 1
            else:
                overdue += amt
                cnt_o += 1

        top_sorted = sorted(top, key=lambda item: -item['days'])[:5]

        return {
            'total': round(total, 2),
            'count': cnt,
            'current': round(current, 2),
            'count_current': cnt_c,
            'due_week': round(due_week, 2),
            'count_week': cnt_w,
            'overdue': round(overdue, 2),
            'count_overdue': cnt_o,
            'top': top_sorted,
        }

    def _get_cash_flow_projection(self, company_ids, today):
        """4 semanas: 2 pasadas (pagos reales) + 2 futuras (CXC/CXP por vencer)."""
        weeks = []
        env = self._accounting_env(company_ids)
        Move = env['account.move']
        Payment = env['account.payment']
        start_offset = -2

        for week_index in range(start_offset, start_offset + 4):
            week_start = today + timedelta(days=week_index * 7)
            week_end = week_start + timedelta(days=6)
            is_future = week_start > today

            if is_future:
                inflow = sum(Move.search([
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'in', ['not_paid', 'partial']),
                    ('invoice_date_due', '>=', week_start),
                    ('invoice_date_due', '<=', week_end),
                    ('company_id', 'in', company_ids),
                ]).mapped('amount_residual'))

                outflow = sum(Move.search([
                    ('move_type', '=', 'in_invoice'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'in', ['not_paid', 'partial']),
                    ('invoice_date_due', '>=', week_start),
                    ('invoice_date_due', '<=', week_end),
                    ('company_id', 'in', company_ids),
                ]).mapped('amount_residual'))
            else:
                inflow = sum(Payment.search([
                    ('payment_type', '=', 'inbound'),
                    ('state', 'in', ['paid', 'in_process']),
                    ('date', '>=', week_start),
                    ('date', '<=', week_end),
                    ('company_id', 'in', company_ids),
                ]).mapped('amount'))

                outflow = sum(Payment.search([
                    ('payment_type', '=', 'outbound'),
                    ('state', 'in', ['paid', 'in_process']),
                    ('date', '>=', week_start),
                    ('date', '<=', week_end),
                    ('company_id', 'in', company_ids),
                ]).mapped('amount'))

            if week_index < 0:
                label = f'Hace {abs(week_index)} sem'
            elif week_index == 0:
                label = 'Esta sem'
            else:
                label = f'Sem +{week_index}'

            weeks.append({
                'label': label,
                'inflow': round(inflow, 2),
                'outflow': round(outflow, 2),
                'net': round(inflow - outflow, 2),
                'is_future': is_future,
            })
        return weeks

    def _get_alerts(self, company_ids, today):
        alerts = []

        cxp_due = self._accounting_env(company_ids)['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('invoice_date_due', '<=', today),
            ('company_id', 'in', company_ids),
        ], limit=5)
        if cxp_due:
            total = sum(cxp_due.mapped('amount_residual'))
            names = ', '.join(cxp_due.mapped('partner_id.name')[:3])
            alerts.append({
                'level': 'danger',
                'msg': (
                    f'CXP vencido: {len(cxp_due)} facturas — '
                    f'L {total:,.0f} — {names}'
                ),
            })

        cxc_crit = self._accounting_env(company_ids)['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('invoice_date_due', '<=', today - timedelta(days=60)),
            ('company_id', 'in', company_ids),
        ])
        if cxc_crit:
            total = sum(cxc_crit.mapped('amount_residual'))
            alerts.append({
                'level': 'warning',
                'msg': (
                    f'CXC crítica: {len(cxc_crit)} facturas >60d — '
                    f'L {total:,.0f} sin cobrar'
                ),
            })

        pending = self.env['kenocia.petty.cash.line'].search([
            ('state', '=', 'delivered'),
            ('petty_cash_id.company_id', 'in', company_ids),
        ])
        if pending:
            total = sum(pending.mapped('amount'))
            names = ', '.join(pending.mapped('employee_id.name')[:2])
            alerts.append({
                'level': 'warning',
                'msg': (
                    f'Caja chica: {len(pending)} anticipo(s) sin '
                    f'factura SAR — L {total:,.0f} — {names}'
                ),
            })

        return alerts

    def _get_filters_meta(self, company_ids):
        companies = self.env['res.company'].search([('id', 'in', company_ids)])
        journals = self._accounting_env(company_ids)['account.journal'].search([
            ('type', 'in', ['bank', 'cash']),
            ('company_id', 'in', company_ids),
        ], order='type, name')
        petty_funds = self.env['kenocia.petty.cash'].search([
            ('company_id', 'in', company_ids),
            ('state', 'in', ['open', 'closed']),
        ])
        return {
            'companies': [
                {'id': company.id, 'name': company.name}
                for company in companies
            ],
            'journals': [
                {
                    'id': journal.id,
                    'name': journal.name,
                    'type': journal.type,
                    'label': (
                        f'{journal.name} (efectivo)'
                        if journal.type == 'cash'
                        else journal.name
                    ),
                }
                for journal in journals
            ],
            'petty_funds': [
                {
                    'id': fund.id,
                    'name': fund.name,
                    'state': fund.state,
                    'label': (
                        f'{fund.name} (cerrado)'
                        if fund.state == 'closed'
                        else fund.name
                    ),
                }
                for fund in petty_funds
            ],
        }
