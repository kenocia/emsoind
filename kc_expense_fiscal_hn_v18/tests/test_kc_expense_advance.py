# -*- coding: utf-8 -*-

from datetime import date

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestKcExpenseAdvance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        manager_group = cls.env.ref('hr_expense.group_hr_expense_manager')
        account_group = cls.env.ref('account.group_account_invoice')
        cls.env.ref('base.user_admin').write({
            'groups_id': [Command.link(manager_group.id), Command.link(account_group.id)],
        })
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))

        cls.advance_account = cls.env['account.account'].create({
            'name': 'Anticipo Empleados Test',
            'code': '110501T',
            'account_type': 'asset_current',
            'reconcile': True,
        })
        cls.payable_account = cls.env['account.account'].search([
            ('account_type', '=', 'liability_payable'),
            ('company_ids', 'in', cls.company.id),
        ], limit=1)
        cls.reimbursement_account = cls.env['account.account'].create({
            'name': 'Reembolso Empleados Test',
            'code': '210501T',
            'account_type': 'liability_payable',
            'reconcile': True,
        })
        cls.company.kc_expense_reimbursement_account_id = cls.reimbursement_account

        cls.misc_journal = cls.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        if not cls.misc_journal:
            cls.misc_journal = cls.env['account.journal'].create({
                'name': 'Misc Test Gastos',
                'code': 'MISCT',
                'type': 'general',
                'company_id': cls.company.id,
            })
        cls.company.kc_expense_fund_journal_id = cls.misc_journal

        cls.cash_journal = cls.env['account.journal'].search([
            ('type', '=', 'cash'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        if not cls.cash_journal.default_account_id:
            cash_account = cls.env['account.account'].search([
                ('account_type', '=', 'asset_cash'),
                ('company_ids', 'in', cls.company.id),
            ], limit=1)
            if cash_account:
                cls.cash_journal.default_account_id = cash_account

        cls.purchase_journal = cls.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.company.expense_journal_id = cls.purchase_journal

        cls.tax_purchase = cls.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('amount', '=', 15),
            ('company_id', '=', cls.company.id),
        ], limit=1)

        cls.expense_account = cls.env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('deprecated', '=', False),
            ('company_ids', 'in', cls.company.id),
        ], limit=1)
        if not cls.expense_account:
            cls.expense_account = cls.env['account.account'].create({
                'name': 'Gastos Test Anticipo',
                'code': '610099T',
                'account_type': 'expense',
            })

        cls.product = cls.env['product.product'].create({
            'name': 'Gasto Anticipo Test',
            'type': 'service',
            'can_be_expensed': True,
            'standard_price': 500.0,
            'list_price': 500.0,
        })
        if cls.expense_account:
            cls.product.property_account_expense_id = cls.expense_account

        cls.partner_employee = cls.env['res.partner'].create({
            'name': 'Empleado Gasto Test',
            'supplier_rank': 1,
            'is_company': False,
        })
        cls.hr_employee = cls.env['hr.employee'].create({
            'name': 'Empleado Gasto Test',
            'work_contact_id': cls.partner_employee.id,
        })
        if cls.payable_account:
            cls.partner_employee.with_company(cls.company).property_account_payable_id = (
                cls.payable_account
            )

        hn = cls.env.ref('base.hn', raise_if_not_found=False)
        vendor_vals = {
            'name': 'Proveedor Gasto SAR Test',
            'supplier_rank': 1,
            'is_company': True,
        }
        if hn:
            vendor_vals.update({
                'country_id': hn.id,
                'vat': '08011990123456',
            })
        cls.vendor = cls.env['res.partner'].create(vendor_vals)
        if cls.payable_account:
            cls.vendor.with_company(cls.company).property_account_payable_id = (
                cls.payable_account
            )

        cls._doc_counter = 0

    @classmethod
    def _next_document_number(cls):
        cls._doc_counter += 1
        return f'000-001-01-0000{cls._doc_counter:04d}'

    def _create_advance(self, amount=1000.0):
        return self.env['kc.expense.advance'].create({
            'employee_id': self.hr_employee.id,
            'amount': amount,
            'account_advance_id': self.advance_account.id,
            'journal_id': self.cash_journal.id,
        })

    def _create_expense_sheet(self, amount=500.0, advance=False, **expense_vals):
        doc_number = expense_vals.pop('kc_document_number', self._next_document_number())
        vals = {
            'name': 'Gasto fiscal test',
            'employee_id': self.hr_employee.id,
            'accounting_date': fields.Date.to_string(date(2022, 1, 15)),
            'expense_line_ids': [Command.create({
                'name': 'Prueba gasto fiscal',
                'employee_id': self.hr_employee.id,
                'product_id': self.product.id,
                'total_amount_currency': amount,
                'tax_ids': [Command.set(self.tax_purchase.ids)] if self.tax_purchase else [],
                'payment_mode': 'own_account',
                'vendor_id': self.vendor.id,
                'kc_document_number': doc_number,
                'kc_document_type': 'factura',
                'kc_cai': 'CAI-TEST-123',
                'kc_document_date': '2022-01-10',
                'company_id': self.company.id,
                'date': '2022-01-10',
                **expense_vals,
            })],
        }
        if advance:
            vals['kc_advance_id'] = advance.id
        return self.env['hr.expense.sheet'].create(vals)

    def _post_expense_sheet(self, sheet):
        sheet.action_submit_sheet()
        sheet.action_approve_expense_sheets()
        sheet.action_sheet_move_post()

    @freeze_time('2022-01-15')
    def test_vendor_bill_partner_is_vendor(self):
        sheet = self._create_expense_sheet(amount=500.0)
        self._post_expense_sheet(sheet)
        expense = sheet.expense_line_ids
        bill = expense.kc_vendor_bill_id
        self.assertTrue(bill)
        self.assertEqual(bill.move_type, 'in_invoice')
        self.assertEqual(bill.partner_id, self.vendor)
        self.assertEqual(bill.correlativo_proveedor, expense.kc_document_number)
        payable_lines = bill.line_ids.filtered(
            lambda line: line.account_id.account_type == 'liability_payable',
        )
        self.assertTrue(payable_lines)

    @freeze_time('2022-01-15')
    def test_fund_clearing_with_advance(self):
        advance = self._create_advance(1000.0)
        advance.action_deliver()
        sheet = self._create_expense_sheet(amount=500.0, advance=advance)
        self._post_expense_sheet(sheet)

        expense = sheet.expense_line_ids
        bill = expense.kc_vendor_bill_id
        self.assertEqual(bill.payment_state, 'paid')
        self.assertTrue(expense.kc_fund_move_id)
        self.assertAlmostEqual(advance.amount_spent, 500.0, places=2)
        self.assertAlmostEqual(advance.amount_balance, 500.0, places=2)

        advance_lines = self.env['account.move.line'].search([
            ('account_id', '=', self.advance_account.id),
            ('partner_id', '=', self.partner_employee.id),
        ])
        reconciled_credits = advance_lines.filtered(
            lambda line: line.credit > 0 and line.reconciled,
        )
        self.assertTrue(reconciled_credits)

    @freeze_time('2022-01-15')
    def test_fund_clearing_without_advance_uses_reimbursement(self):
        sheet = self._create_expense_sheet(amount=500.0)
        self._post_expense_sheet(sheet)
        expense = sheet.expense_line_ids
        fund_move = expense.kc_fund_move_id
        self.assertTrue(fund_move)
        reimb_lines = fund_move.line_ids.filtered(
            lambda line: line.account_id == self.reimbursement_account,
        )
        self.assertTrue(reimb_lines)
        self.assertAlmostEqual(reimb_lines.credit, 500.0, places=2)

    @freeze_time('2022-01-15')
    def test_register_payment_blocked_for_fiscal_expenses(self):
        sheet = self._create_expense_sheet(amount=500.0)
        self._post_expense_sheet(sheet)
        with self.assertRaises(UserError):
            sheet.action_register_payment()

    @freeze_time('2022-01-15')
    def test_company_paid_fiscal_creates_open_vendor_bill(self):
        sheet = self._create_expense_sheet(
            amount=500.0,
            payment_mode='company_account',
        )
        self._post_expense_sheet(sheet)
        expense = sheet.expense_line_ids
        bill = expense.kc_vendor_bill_id
        self.assertTrue(bill)
        self.assertEqual(bill.move_type, 'in_invoice')
        self.assertEqual(bill.partner_id, self.vendor)
        self.assertEqual(bill.state, 'posted')
        self.assertIn(bill.payment_state, ('not_paid', 'partial'))
        self.assertFalse(expense.kc_fund_move_id)
        with self.assertRaises(UserError):
            sheet.action_register_payment()

    @freeze_time('2022-01-15')
    def test_close_advance_balanced(self):
        advance = self._create_advance(500.0)
        advance.action_deliver()
        sheet = self._create_expense_sheet(amount=500.0, advance=advance)
        self._post_expense_sheet(sheet)

        wizard = self.env['kc.expense.advance.close.wizard'].create({
            'advance_id': advance.id,
            'amount_balance': advance.amount_balance,
        })
        wizard.action_confirm_close()
        self.assertEqual(advance.state, 'closed')

    @freeze_time('2022-01-15')
    def test_close_advance_surplus(self):
        advance = self._create_advance(1000.0)
        advance.action_deliver()
        sheet = self._create_expense_sheet(amount=500.0, advance=advance)
        self._post_expense_sheet(sheet)

        wizard = self.env['kc.expense.advance.close.wizard'].create({
            'advance_id': advance.id,
            'amount_balance': advance.amount_balance,
            'journal_id': self.cash_journal.id,
        })
        wizard.action_confirm_close()
        self.assertEqual(advance.state, 'closed')
        self.assertTrue(advance.closing_move_id)

    @freeze_time('2022-01-15')
    def test_excess_expense_uses_reimbursement_when_advance_exhausted(self):
        advance = self._create_advance(500.0)
        advance.action_deliver()
        sheet = self._create_expense_sheet(amount=800.0, advance=advance)
        self._post_expense_sheet(sheet)

        expense = sheet.expense_line_ids
        fund_move = expense.kc_fund_move_id
        advance_credit = sum(fund_move.line_ids.filtered(
            lambda line: line.account_id == self.advance_account and line.credit > 0,
        ).mapped('credit'))
        reimb_credit = sum(fund_move.line_ids.filtered(
            lambda line: line.account_id == self.reimbursement_account and line.credit > 0,
        ).mapped('credit'))
        self.assertAlmostEqual(advance_credit, 500.0, places=2)
        self.assertAlmostEqual(reimb_credit, 300.0, places=2)
        self.assertAlmostEqual(advance.amount_spent, 500.0, places=2)

    @freeze_time('2022-01-15')
    def test_book_purchases_reads_vendor_for_expense_moves(self):
        doc_number = self._next_document_number()
        advance = self._create_advance(1000.0)
        advance.action_deliver()
        sheet = self._create_expense_sheet(
            amount=500.0,
            advance=advance,
            kc_document_number=doc_number,
        )
        self._post_expense_sheet(sheet)

        book = self.env['kc_fiscal_hn.book.purchases'].create({
            'date_from': date(2022, 1, 1),
            'date_to': date(2022, 1, 31),
            'company_id': self.company.id,
        })
        book.action_generate()
        expense_lines = book.line_ids.filtered(
            lambda line: line.numero_factura == doc_number,
        )
        self.assertTrue(expense_lines)
        self.assertEqual(expense_lines[0].rtn_proveedor, self.vendor.vat)
        self.assertEqual(expense_lines[0].proveedor, self.vendor.name)

    @freeze_time('2022-01-15')
    def test_single_open_advance_per_employee(self):
        advance1 = self._create_advance(1000.0)
        advance1.action_deliver()
        with self.assertRaises(UserError):
            advance2 = self._create_advance(500.0)
            advance2.action_deliver()

    def test_cai_required_for_mediano_grande_on_factura(self):
        self.company.tipo_contribuyente = 'mediano'
        with self.assertRaises(ValidationError):
            self.env['hr.expense'].create({
                'name': 'Gasto sin CAI',
                'employee_id': self.hr_employee.id,
                'product_id': self.product.id,
                'total_amount_currency': 100.0,
                'kc_document_type': 'factura',
                'kc_document_number': '000-001-01-99999999',
                'vendor_id': self.vendor.id,
                'company_id': self.company.id,
            })

    def test_fiscal_vendor_required(self):
        with self.assertRaises(ValidationError):
            self.env['hr.expense'].create({
                'name': 'Gasto sin proveedor',
                'employee_id': self.hr_employee.id,
                'product_id': self.product.id,
                'total_amount_currency': 100.0,
                'kc_document_number': '000-001-01-00009999',
                'company_id': self.company.id,
            })
