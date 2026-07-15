# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3
"""Pruebas de los 3 escenarios de pago/dispersión masiva."""

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestKenociaDispersion(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tesoreria_admin = cls.env.ref('kenocia_tesoreria_v18.group_tesoreria_admin')
        cls.env.ref('base.user_admin').write({
            'group_ids': [(4, cls.tesoreria_admin.id)],
        })
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))
        cls.company = cls.env.company

        cls.bank = cls.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', cls.company.id),
        ], limit=1) or cls.env['account.journal'].create({
            'name': 'Banco Dispersión Test',
            'type': 'bank',
            'code': 'KTDB',
        })

        cls.income_account = cls.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.expense_account = cls.env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.sale_journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.purchase_journal = cls.env['account.journal'].search([
            ('type', '=', 'purchase'), ('company_id', '=', cls.company.id),
        ], limit=1)

        cls.customer = cls.env['res.partner'].create({
            'name': 'Cliente Dispersión Test',
            'customer_rank': 1,
        })
        cls.vendor_a = cls.env['res.partner'].create({
            'name': 'Proveedor A Test', 'supplier_rank': 1,
        })
        cls.vendor_b = cls.env['res.partner'].create({
            'name': 'Proveedor B Test', 'supplier_rank': 1,
        })
        for vendor in (cls.vendor_a, cls.vendor_b):
            cls.env['res.partner.bank'].create({
                'acc_number': 'HN%s' % vendor.id,
                'partner_id': vendor.id,
            })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @classmethod
    def _create_invoice(cls, partner, move_type, amount):
        account = cls.income_account if move_type == 'out_invoice' else cls.expense_account
        journal = cls.sale_journal if move_type == 'out_invoice' else cls.purchase_journal
        invoice = cls.env['account.move'].create({
            'move_type': move_type,
            'partner_id': partner.id,
            'invoice_date': '2026-06-01',
            'journal_id': journal.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Línea test',
                'quantity': 1,
                'price_unit': amount,
                'account_id': account.id,
            })],
        })
        invoice.action_post()
        return invoice

    # ------------------------------------------------------------------
    # Escenario 1 — Pago/Cobro masivo (un contacto)
    # ------------------------------------------------------------------
    def test_esc1_mass_payment_full_and_partial(self):
        """Un cliente, 2 facturas: una total y una parcial, un solo cobro."""
        inv1 = self._create_invoice(self.customer, 'out_invoice', 1000)
        inv2 = self._create_invoice(self.customer, 'out_invoice', 500)

        wizard = self.env['kenocia.mass.payment.wizard'].with_context(
            default_operation='cxc',
        ).create({
            'partner_id': self.customer.id,
            'journal_id': self.bank.id,
            'payment_date': '2026-06-10',
        })
        wizard._onchange_load_lines()
        self.assertEqual(len(wizard.line_ids), 2)

        # inv1 total (1000), inv2 parcial (300 de 500)
        for line in wizard.line_ids:
            if line.move_id == inv2:
                line.amount_to_pay = 300

        action = wizard.action_confirm()
        payment = self.env['account.payment'].browse(action['res_id'])
        self.assertAlmostEqual(payment.amount, 1300, places=2)

        inv1.invalidate_recordset(['amount_residual', 'payment_state'])
        inv2.invalidate_recordset(['amount_residual'])
        self.assertTrue(inv1.currency_id.is_zero(inv1.amount_residual))
        self.assertAlmostEqual(inv2.amount_residual, 200, places=2)

    # ------------------------------------------------------------------
    # Escenario 2 — Dispersión a proveedores (multi-proveedor)
    # ------------------------------------------------------------------
    def test_esc2_vendor_dispersion_creates_payment_per_partner(self):
        bill_a = self._create_invoice(self.vendor_a, 'in_invoice', 800)
        bill_b = self._create_invoice(self.vendor_b, 'in_invoice', 1200)

        wizard = self.env['kenocia.vendor.dispersion.wizard'].create({
            'journal_id': self.bank.id,
            'payment_date': '2026-06-10',
            'partner_ids': [(6, 0, (self.vendor_a + self.vendor_b).ids)],
        })
        wizard.action_load_invoices()
        self.assertEqual(len(wizard.line_ids), 2)

        wizard.action_confirm()
        payments = self.env['account.payment'].search([
            ('partner_id', 'in', (self.vendor_a + self.vendor_b).ids),
            ('payment_type', '=', 'outbound'),
        ])
        self.assertEqual(len(payments), 2)

        bill_a.invalidate_recordset(['amount_residual'])
        bill_b.invalidate_recordset(['amount_residual'])
        self.assertTrue(bill_a.currency_id.is_zero(bill_a.amount_residual))
        self.assertTrue(bill_b.currency_id.is_zero(bill_b.amount_residual))

    def test_esc2_blocks_vendor_without_bank(self):
        vendor_no_bank = self.env['res.partner'].create({
            'name': 'Proveedor Sin Banco', 'supplier_rank': 1,
        })
        self._create_invoice(vendor_no_bank, 'in_invoice', 500)
        wizard = self.env['kenocia.vendor.dispersion.wizard'].create({
            'journal_id': self.bank.id,
            'payment_date': '2026-06-10',
            'partner_ids': [(6, 0, vendor_no_bank.ids)],
        })
        wizard.action_load_invoices()
        with self.assertRaises(UserError):
            wizard.action_confirm()

    # ------------------------------------------------------------------
    # Motor de dispersión — conciliación parcial controlada
    # ------------------------------------------------------------------
    def test_engine_partial_reconcile_amount(self):
        """El motor debe respetar el monto parcial exacto por documento."""
        bill = self._create_invoice(self.vendor_a, 'in_invoice', 1000)
        payable_line = bill.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable',
        )
        engine = self.env['kenocia.dispersion.engine']
        spec = {
            'partner': self.vendor_a,
            'partner_type': 'supplier',
            'payment_type': 'outbound',
            'account': payable_line.account_id,
            'allocations': [(payable_line, 400)],
        }
        engine.kenocia_run_dispersion(
            [spec], self.bank, '2026-06-10', group_into_batch=False,
        )
        bill.invalidate_recordset(['amount_residual'])
        self.assertAlmostEqual(bill.amount_residual, 600, places=2)

    def test_engine_rejects_overpay(self):
        bill = self._create_invoice(self.vendor_b, 'in_invoice', 300)
        payable_line = bill.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable',
        )
        engine = self.env['kenocia.dispersion.engine']
        with self.assertRaises(UserError):
            engine.kenocia_check_allocation_amount(payable_line, 400)
