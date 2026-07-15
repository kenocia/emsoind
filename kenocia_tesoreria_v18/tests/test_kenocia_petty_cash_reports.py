# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.kenocia_tesoreria_v18.tests.test_kenocia_petty_cash import TestKenociaPettyCash


@tagged('post_install', '-at_install')
class TestPettyCashReports(TestKenociaPettyCash):

    def _create_report_wizard(self, **extra):
        values = {
            'date_from': '2026-05-01',
            'date_to': '2026-05-31',
            'company_id': self.env.company.id,
        }
        values.update(extra)
        return self.env['kenocia.petty.cash.report.wizard'].create(values)

    def test_operational_report_data(self):
        fund = self._create_fund(amount=3000.0)
        fund.action_open_fund()
        line = self._create_line(fund, 600.0)
        line.action_confirm_delivery()
        bill = self._create_vendor_bill(450.0)
        self.env['kenocia.petty.cash.settlement'].create({
            'line_id': line.id,
            'partner_id': bill.partner_id.id,
            'invoice_id': bill.id,
            'settlement_date': '2026-05-17',
        }).action_confirm_settlement()

        wizard = self._create_report_wizard(
            report_type='operational',
            fund_ids=[(6, 0, [fund.id])],
        )
        data = wizard._get_report_data()

        self.assertEqual(len(data['funds']), 1)
        fund_data = data['funds'][0]
        self.assertEqual(fund_data['total_delivered'], 600.0)
        self.assertEqual(fund_data['total_settled'], 600.0)
        self.assertEqual(fund_data['total_pending'], 0.0)
        self.assertEqual(data['total_global_delivered'], 600.0)
        self.assertEqual(data['total_global_settled'], 600.0)

    def test_fiscal_report_only_settled(self):
        fund = self._create_fund()
        fund.action_open_fund()
        delivered_line = self._create_line(fund, 300.0)
        delivered_line.action_confirm_delivery()
        settled_line = self._create_line(fund, 600.0)
        settled_line.write({'date': '2026-05-16'})
        settled_line.action_confirm_delivery()
        bill = self._create_vendor_bill(450.0)
        self.env['kenocia.petty.cash.settlement'].create({
            'line_id': settled_line.id,
            'partner_id': bill.partner_id.id,
            'invoice_id': bill.id,
            'settlement_date': '2026-05-17',
        }).action_confirm_settlement()

        wizard = self._create_report_wizard(report_type='fiscal')
        data = wizard._get_fiscal_data()

        self.assertEqual(data['count'], 1)
        self.assertEqual(data['rows'][0]['empleado'], settled_line.employee_id.display_name)
        self.assertEqual(data['rows'][0]['total_factura'], bill.amount_total)

    def test_close_fund_blocks_pending_advances(self):
        fund = self._create_fund()
        fund.action_open_fund()
        line = self._create_line(fund, 800.0)
        line.action_confirm_delivery()
        with self.assertRaises(UserError):
            fund.action_close_fund()

    def test_close_fund_generates_return_entry(self):
        fund = self._create_fund(amount=2000.0)
        fund.action_open_fund()
        self.assertEqual(fund.amount_available, 2000.0)

        bank_account = self.bank_journal.default_account_id
        cash_account = self.cash_journal.default_account_id
        self.assertTrue(bank_account)
        self.assertTrue(cash_account)

        wizard = self.env['kenocia.petty.cash.close.wizard'].create({
            'fund_id': fund.id,
            'amount_physical': 2000.0,
            'journal_return_id': self.bank_journal.id,
        })
        wizard.action_confirm_close()

        self.assertEqual(fund.state, 'closed')
        self.assertTrue(fund.close_move_return_id)
        move = fund.close_move_return_id
        self.assertEqual(move.state, 'posted')
        self.assertAlmostEqual(
            sum(move.line_ids.filtered(
                lambda line: line.account_id == bank_account,
            ).mapped('debit')),
            2000.0,
        )
        self.assertAlmostEqual(
            sum(move.line_ids.filtered(
                lambda line: line.account_id == cash_account,
            ).mapped('credit')),
            2000.0,
        )

    def test_close_fund_zero_balance_no_entry(self):
        bill = self._create_vendor_bill(870.0)
        fund = self._create_fund(amount=bill.amount_total)
        fund.action_open_fund()
        line = self._create_line(fund, bill.amount_total)
        line.action_confirm_delivery()
        self.env['kenocia.petty.cash.settlement'].create({
            'line_id': line.id,
            'partner_id': bill.partner_id.id,
            'invoice_id': bill.id,
            'settlement_date': '2026-05-20',
        }).action_confirm_settlement()
        self.assertAlmostEqual(fund.amount_available, 0.0, places=2)

        wizard = self.env['kenocia.petty.cash.close.wizard'].create({
            'fund_id': fund.id,
            'amount_physical': 0.0,
            'journal_return_id': self.bank_journal.id,
        })
        wizard.action_confirm_close()

        self.assertEqual(fund.state, 'closed')
        self.assertFalse(fund.close_move_return_id)
