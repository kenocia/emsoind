# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestKenociaAdvancePayment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tesoreria_admin = cls.env.ref('kenocia_tesoreria_v18.group_tesoreria_admin')
        cls.env.ref('base.user_admin').write({
            'group_ids': [(4, cls.tesoreria_admin.id)],
        })
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))

        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente Adelantos Test',
            'customer_rank': 1,
        })
        cls.journal_bank = cls.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)
        if not cls.journal_bank:
            cls.journal_bank = cls.env['account.journal'].create({
                'name': 'Banco Adelantos Test',
                'type': 'bank',
                'code': 'KTAD',
            })

        cls.product = cls.env['product.product'].create({
            'name': 'Producto Test Adelanto',
            'list_price': 100000.0,
            'type': 'service',
        })

        cls.advance_account_cxc = cls.env['account.account'].create({
            'name': 'Anticipos Clientes Test',
            'code': '209010T',
            'account_type': 'asset_current',
            'reconcile': True,
        })
        cls.env.company.write({
            'kenocia_advance_account_cxc_id': cls.advance_account_cxc.id,
        })

        cls.sale_journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

    def _create_confirmed_sale_order(self, amount=100000.0):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'price_unit': amount,
            })],
        })
        order.action_confirm()
        return order

    def _create_advance(self, order, amount, **kwargs):
        values = {
            'advance_type': 'customer',
            'partner_id': self.partner.id,
            'sale_order_id': order.id,
            'journal_id': self.journal_bank.id,
            'advance_account_id': self.advance_account_cxc.id,
            'amount': amount,
            'date': '2026-06-02',
        }
        values.update(kwargs)
        return self.env['kenocia.advance.payment'].create(values)

    def test_advance_customer_creation(self):
        """TEST-08: adelanto creado en borrador con partner y SO."""
        order = self._create_confirmed_sale_order()
        advance = self._create_advance(order, 50000)
        self.assertEqual(advance.state, 'draft')
        self.assertEqual(advance.partner_id, self.partner)
        self.assertEqual(advance.sale_order_id, order)
        self.assertEqual(advance.amount_residual, 50000)

    def test_advance_confirm_creates_payment(self):
        """TEST-09: action_confirm_advance crea account.payment sin factura."""
        order = self._create_confirmed_sale_order()
        advance = self._create_advance(order, 50000)
        advance.action_confirm_advance()
        self.assertEqual(advance.state, 'confirmed')
        self.assertTrue(advance.payment_id)
        self.assertFalse(advance.advance_invoice_id)
        if advance.payment_id.move_id:
            self.assertTrue(advance.payment_id.move_id)
        self.assertNotEqual(advance.name, '/')
        self.assertEqual(advance.payment_id.amount, 50000)

    def test_advance_amount_vs_order_constraint(self):
        """TEST-10: ValidationError si monto > total orden."""
        order = self._create_confirmed_sale_order(amount=50000)
        with self.assertRaises(ValidationError):
            self._create_advance(order, 60000)

    def test_advance_apply_to_invoice_full(self):
        """TEST-11: factura pagada tras aplicar adelanto total (auto al publicar)."""
        order = self._create_confirmed_sale_order()
        advance = self._create_advance(order, 100000)
        advance.action_confirm_advance()
        invoice = order._create_invoices()
        invoice.action_post()
        self.assertEqual(advance.state, 'fully_applied')
        self.assertEqual(advance.amount_residual, 0)
        self.assertIn(invoice, advance.invoice_ids)
        invoice.invalidate_recordset(['payment_state', 'amount_residual'])
        self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))

    def test_advance_apply_to_invoice_partial(self):
        """TEST-12: aplicación parcial con saldo residual correcto."""
        order = self._create_confirmed_sale_order()
        advance = self._create_advance(order, 60000)
        advance.action_confirm_advance()
        invoice = order._create_invoices()
        invoice.action_post()
        self.assertEqual(advance.state, 'fully_applied')
        self.assertAlmostEqual(invoice.amount_residual, 40000, places=2)

    def test_advance_currency_mismatch(self):
        """TEST-13: ValidationError si moneda del adelanto != factura."""
        other_currency = self.env['res.currency'].search([
            ('id', '!=', self.env.company.currency_id.id),
        ], limit=1)
        if not other_currency:
            self.skipTest('No hay moneda alternativa para probar mismatch.')
        order = self._create_confirmed_sale_order()
        advance = self._create_advance(order, 50000)
        advance.action_confirm_advance()
        invoice = order._create_invoices()
        invoice.currency_id = other_currency
        invoice.with_context(
            kenocia_skip_auto_apply_advance=True,
        ).action_post()
        with self.assertRaises(ValidationError):
            advance._apply_to_invoice(invoice, 50000)

    def test_advance_cancel_with_applications_blocked(self):
        """TEST-14: UserError al cancelar adelanto con aplicaciones."""
        order = self._create_confirmed_sale_order()
        advance = self._create_advance(order, 60000)
        advance.action_confirm_advance()
        invoice = order._create_invoices()
        invoice.action_post()
        with self.assertRaises(UserError):
            advance.action_cancel_advance()

    def test_smart_button_count_sale_order(self):
        """TEST-18: advance_count y amount_due en SO."""
        order = self._create_confirmed_sale_order()
        advance = self._create_advance(order, 30000)
        advance.action_confirm_advance()
        order.invalidate_recordset([
            'advance_count', 'advance_amount_total', 'amount_due',
        ])
        self.assertEqual(order.advance_count, 1)
        self.assertEqual(order.advance_amount_total, 30000)
        self.assertAlmostEqual(order.amount_due, 70000, places=2)

    def test_advance_receipt_report_values(self):
        order = self._create_confirmed_sale_order()
        advance = self._create_advance(order, 50000)
        advance.notes = 'Anticipo para proyecto piloto.'
        advance.action_confirm_advance()
        values = advance._get_advance_receipt_report_values()
        self.assertEqual(values['receipt_partner'], advance.partner_id)
        self.assertEqual(len(values['receipt_documents']), 1)
        self.assertEqual(values['receipt_documents'][0]['name'], order.name)
        self.assertEqual(values['advance_note'], 'Anticipo para proyecto piloto.')
        self.assertIn('Saldo pendiente', values['advance_standard_note'])

    def test_apply_advance_wizard(self):
        order = self._create_confirmed_sale_order()
        advance = self._create_advance(order, 50000)
        advance.action_confirm_advance()
        invoice = order._create_invoices()
        invoice.with_context(
            kenocia_skip_auto_apply_advance=True,
        ).action_post()
        wizard = self.env['kenocia.apply.advance.wizard'].with_context(
            default_invoice_id=invoice.id,
        ).create({})
        self.assertTrue(wizard.line_ids)
        wizard.line_ids.write({'amount_to_apply': 50000})
        wizard.action_apply()
        self.assertEqual(advance.state, 'fully_applied')
