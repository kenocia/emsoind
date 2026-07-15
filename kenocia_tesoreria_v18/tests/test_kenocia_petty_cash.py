# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestKenociaPettyCash(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_admin = cls.env.ref('kenocia_tesoreria_v18.group_tesoreria_admin')
        cls.env.ref('base.user_admin').write({
            'group_ids': [(4, cls.group_admin.id)],
        })
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))

        cls.bridge_account = cls.env['account.account'].create({
            'name': 'Tránsito Caja Chica Test',
            'code': '210106T',
            'account_type': 'liability_payable',
            'reconcile': True,
        })
        cls.payable_account = cls.env['account.account'].search([
            ('account_type', '=', 'liability_payable'),
            ('id', '!=', cls.bridge_account.id),
            ('company_ids', 'in', cls.env.company.id),
        ], limit=1)
        if not cls.payable_account:
            cls.payable_account = cls.env['account.account'].create({
                'name': 'Proveedores Test CC',
                'code': '210107T',
                'account_type': 'liability_payable',
                'reconcile': True,
            })

        cls.cash_journal = cls.env['account.journal'].search([
            ('type', '=', 'cash'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)
        if not cls.cash_journal:
            cls.cash_journal = cls.env['account.journal'].create({
                'name': 'Caja Chica Test',
                'type': 'cash',
                'code': 'CSH1',
            })

        cls.bank_journal = cls.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)
        if not cls.bank_journal:
            cls.bank_journal = cls.env['account.journal'].create({
                'name': 'Banco Test CC',
                'type': 'bank',
                'code': 'BNKCC',
            })

        cls.custodian = cls.env['res.partner'].create({'name': 'Custodio Test'})
        cls.employee = cls.env['res.partner'].create({'name': 'Empleado Test CC'})
        hn = cls.env.ref('base.hn', raise_if_not_found=False)
        vendor_vals = {
            'name': 'Proveedor SAR Test',
            'supplier_rank': 1,
            'is_company': True,
        }
        if hn:
            vendor_vals.update({
                'country_id': hn.id,
                'vat': '08011990123456',
            })
        cls.vendor = cls.env['res.partner'].create(vendor_vals)
        cls.vendor.with_company(cls.env.company).property_account_payable_id = (
            cls.payable_account
        )

        cls.purchase_journal = cls.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)
        if cls.purchase_journal:
            cls.purchase_journal.document_fiscal = 'vendors'

        cls.product = cls.env['product.product'].create({
            'name': 'Gasto Caja Chica Test',
            'type': 'service',
            'standard_price': 500.0,
            'list_price': 500.0,
        })
        expense_account = cls.env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('company_ids', 'in', cls.env.company.id),
        ], limit=1)
        if expense_account:
            cls.product.property_account_expense_id = expense_account

    def _create_fund(self, amount=5000.0):
        return self.env['kenocia.petty.cash'].create({
            'name': 'Fondo Test Mayo 2026',
            'journal_id': self.cash_journal.id,
            'account_bridge_id': self.bridge_account.id,
            'custodian_id': self.custodian.id,
            'date_from': '2026-05-01',
            'date_to': '2026-05-31',
            'amount_authorized': amount,
        })

    def _create_line(self, fund, amount=500.0):
        return self.env['kenocia.petty.cash.line'].create({
            'petty_cash_id': fund.id,
            'employee_id': self.employee.id,
            'description': 'Compra repuestos',
            'amount': amount,
            'date': '2026-05-15',
        })

    def _create_vendor_bill(self, amount=500.0):
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.vendor.id,
            'invoice_date': '2026-05-16',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': amount,
            })],
            'cai_proveedor': 'CAI-TEST-001',
            'correlativo_proveedor': '001-001-01-00000099',
            'femision_proveedor': '2026-05-16',
            'class_document_sar': 'FA',
            'montos_sar': 'gasto',
        }
        if self.purchase_journal:
            bill_vals['journal_id'] = self.purchase_journal.id
        bill = self.env['account.move'].create(bill_vals)
        bill.action_post()
        return bill

    def test_petty_cash_fund_open(self):
        fund = self._create_fund()
        self.assertEqual(fund.state, 'draft')
        fund.action_open_fund()
        self.assertEqual(fund.state, 'open')
        self.assertEqual(fund.amount_available, 5000.0)

    def test_petty_cash_delivery_without_payment(self):
        """Entrega física: solo control operativo, sin account.payment."""
        fund = self._create_fund()
        fund.action_open_fund()
        line = self._create_line(fund, 1300.0)
        line.action_confirm_delivery()
        self.assertEqual(line.state, 'delivered')
        self.assertFalse(line.settlement_payment_id)
        self.assertEqual(fund.amount_delivered, 1300.0)
        self.assertEqual(fund.amount_available, 3700.0)

    def test_petty_cash_recharge_accounting(self):
        """Recarga: banco→puente (tránsito) y puente→caja (recepción)."""
        fund = self._create_fund(amount=1000.0)
        fund.action_open_fund()
        bank_account = self.bank_journal.default_account_id
        cash_account = self.cash_journal.default_account_id
        self.assertTrue(bank_account)
        self.assertTrue(cash_account)

        recharge = self.env['kenocia.petty.cash.recharge'].create({
            'petty_cash_id': fund.id,
            'amount': 500.0,
            'journal_source_id': self.bank_journal.id,
            'reference': 'CHQ-001',
        })
        recharge.action_send_to_transit()

        payment_move = recharge.payment_bank_id.move_id
        bridge_debit = sum(
            payment_move.line_ids.filtered(
                lambda line: line.account_id == self.bridge_account,
            ).mapped('debit'),
        )
        bank_credit = sum(
            payment_move.line_ids.filtered(
                lambda line: line.account_id == bank_account,
            ).mapped('credit'),
        )
        self.assertAlmostEqual(bridge_debit, 500.0)
        self.assertAlmostEqual(bank_credit, 500.0)

        recharge.action_confirm_cash_received()
        receipt_move = recharge.move_receipt_id
        cash_debit = sum(
            receipt_move.line_ids.filtered(
                lambda line: line.account_id == cash_account,
            ).mapped('debit'),
        )
        bridge_credit = sum(
            receipt_move.line_ids.filtered(
                lambda line: line.account_id == self.bridge_account,
            ).mapped('credit'),
        )
        self.assertAlmostEqual(cash_debit, 500.0)
        self.assertAlmostEqual(bridge_credit, 500.0)

    def test_petty_cash_recharge_increases_available(self):
        fund = self._create_fund(amount=1000.0)
        fund.action_open_fund()
        recharge = self.env['kenocia.petty.cash.recharge'].create({
            'petty_cash_id': fund.id,
            'amount': 500.0,
            'journal_source_id': self.bank_journal.id,
            'reference': 'CHQ-001',
        })
        recharge.action_send_to_transit()
        self.assertEqual(recharge.state, 'in_transit')
        recharge.action_confirm_cash_received()
        self.assertEqual(recharge.state, 'received')
        self.assertEqual(fund.recharge_total, 500.0)
        self.assertEqual(fund.amount_available, 1500.0)

    def test_petty_cash_settlement_pays_invoice(self):
        """Liquidación SAR: pago desde caja chica y vuelto al fondo."""
        fund = self._create_fund()
        fund.action_open_fund()
        line = self._create_line(fund, 600.0)
        line.action_confirm_delivery()
        bill = self._create_vendor_bill(450.0)

        wizard = self.env['kenocia.petty.cash.settlement'].create({
            'line_id': line.id,
            'partner_id': bill.partner_id.id,
            'invoice_id': bill.id,
            'settlement_date': '2026-05-17',
        })
        wizard.action_confirm_settlement()

        self.assertEqual(line.state, 'settled')
        self.assertEqual(line.invoice_id, bill)
        self.assertEqual(line.amount_invoice, bill.amount_total)
        expected_return = 600.0 - bill.amount_total
        self.assertEqual(line.amount_returned, expected_return)
        self.assertTrue(line.settlement_payment_id)
        self.assertIn(bill.payment_state, ('paid', 'in_payment', 'partial'))
        self.assertEqual(fund.amount_settled, 600.0)
        self.assertEqual(fund.amount_pending, 0.0)
        self.assertEqual(fund.amount_available, 5000.0 - 600.0 + expected_return)

    def test_petty_cash_settlement_foreign_vendor(self):
        """Proveedor extranjero: visible en wizard y sin exigir CAI/correlativo local."""
        us = self.env.ref('base.us', raise_if_not_found=False)
        if not us:
            self.skipTest('País US no disponible en base.')
        foreign_vendor = self.env['res.partner'].create({
            'name': 'Intcomex Test Foreign',
            'supplier_rank': 1,
            'is_company': True,
            'country_id': us.id,
            'vat': '2732784378',
        })
        foreign_vendor.with_company(self.env.company).property_account_payable_id = (
            self.payable_account
        )
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': foreign_vendor.id,
            'invoice_date': '2026-05-16',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': 450.0,
            })],
            'montos_sar': 'gasto',
        }
        if self.purchase_journal:
            bill_vals['journal_id'] = self.purchase_journal.id
        bill = self.env['account.move'].create(bill_vals)
        bill.action_post()

        self.assertFalse(bill._kenocia_get_petty_cash_fiscal_errors())

        fund = self._create_fund()
        fund.action_open_fund()
        line = self._create_line(fund, 600.0)
        line.action_confirm_delivery()

        wizard = self.env['kenocia.petty.cash.settlement'].create({
            'line_id': line.id,
            'partner_id': foreign_vendor.id,
            'invoice_id': bill.id,
            'settlement_date': '2026-05-17',
        })
        wizard.action_confirm_settlement()
        self.assertEqual(line.state, 'settled')
        self.assertEqual(line.invoice_id, bill)

    def test_petty_cash_cannot_close_with_pending(self):
        fund = self._create_fund()
        fund.action_open_fund()
        line = self._create_line(fund, 800.0)
        line.action_confirm_delivery()
        with self.assertRaises(UserError):
            fund.action_close_fund()
