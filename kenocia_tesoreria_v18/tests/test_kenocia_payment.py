# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestKenociaPayment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tesoreria_admin = cls.env.ref('kenocia_tesoreria_v18.group_tesoreria_admin')
        cls.env.ref('base.user_admin').write({
            'group_ids': [(4, cls.tesoreria_admin.id)],
        })
        cls.supervisor = cls.env.ref('base.user_admin')
        cls.env = cls.env(user=cls.supervisor)

        cls.partner = cls.env['res.partner'].create({
            'name': 'Proveedor Test Tesorería',
            'supplier_rank': 1,
        })
        cls.journal_bank = cls.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)
        if not cls.journal_bank:
            cls.journal_bank = cls.env['account.journal'].create({
                'name': 'Banco Test Tesorería',
                'type': 'bank',
                'code': 'KTBP',
            })

        cls.sequence_cheque = cls.env['kenocia.sequence'].create({
            'name': 'Cheques Test',
            'journal_id': cls.journal_bank.id,
            'transaction_type': 'cheque',
            'prefix': 'CHQ/TST/',
            'next_number': 1,
            'padding': 4,
        })

    def _create_treasury_payment(self, **kwargs):
        values = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner.id,
            'amount': 1000.0,
            'journal_id': self.journal_bank.id,
            'tesoreria_type': 'cheque',
        }
        values.update(kwargs)
        return self.env['account.payment'].create(values)

    def test_payment_gets_sequence_name(self):
        """TEST-04: move_id.name == secuencia al hacer action_post()."""
        payment = self._create_treasury_payment()
        payment.action_post()
        self.assertTrue(payment.move_id)
        self.assertEqual(payment.move_id.name, 'CHQ/TST/0001')
        self.assertEqual(payment.kenocia_sequence_name, 'CHQ/TST/0001')
        self.assertEqual(payment.kenocia_seq_id, self.sequence_cheque)
        self.assertEqual(self.sequence_cheque.next_number, 2)

    def test_no_sequence_uses_native(self):
        """TEST-05: sin secuencia Kenocia, el pago usa numeración nativa (no bloquea)."""
        payment = self._create_treasury_payment(tesoreria_type='deposito')
        payment.action_post()
        self.assertTrue(payment.move_id)
        self.assertFalse(payment.kenocia_seq_id)
        self.assertFalse(payment.kenocia_sequence_name)
        self.assertTrue(payment.move_id.name)
        self.assertNotEqual(payment.move_id.name, '/')

    def test_type_immutable_when_posted(self):
        """TEST-06: ValidationError al cambiar tesoreria_type de un pago publicado."""
        payment = self._create_treasury_payment()
        payment.action_post()
        with self.assertRaises(ValidationError):
            payment.write({'tesoreria_type': 'deposito'})

    def test_void_cheque_registers_gap(self):
        """TEST-07: void_count+1, state=canceled, número no reutilizado."""
        payment = self._create_treasury_payment()
        payment.action_post()
        next_before_void = self.sequence_cheque.next_number
        payment._action_void_cheque_confirm('Cheque extraviado')
        self.assertEqual(self.sequence_cheque.void_count, 1)
        self.assertTrue(payment.is_void_cheque)
        self.assertEqual(payment.state, 'canceled')
        self.assertEqual(self.sequence_cheque.next_number, next_before_void)

    def test_standard_payment_unaffected(self):
        """TEST-15: pagos sin tesoreria_type mantienen flujo estándar."""
        payment = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner.id,
            'amount': 500.0,
            'journal_id': self.journal_bank.id,
        })
        payment.action_post()
        self.assertFalse(payment.kenocia_seq_id)
        self.assertFalse(payment.kenocia_sequence_name)

    def test_void_cheque_requires_supervisor(self):
        cxc_user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Usuario CXC Test',
            'login': 'cxc_test_tesoreria',
            'group_ids': [(6, 0, [
                self.env.ref('kenocia_tesoreria_v18.group_tesoreria_cxc').id,
                self.env.ref('base.group_user').id,
                self.env.ref('account.group_account_invoice').id,
            ])],
        })
        payment = self._create_treasury_payment()
        payment.action_post()
        with self.assertRaises(UserError):
            payment.with_user(cxc_user).action_void_cheque()

    def test_get_formview_id_by_tesoreria_type(self):
        """Vista primaria según tesoreria_type al abrir el pago."""
        cheque = self._create_treasury_payment(tesoreria_type='cheque')
        transfer = self._create_treasury_payment(tesoreria_type='transferencia')
        cash = self._create_treasury_payment(tesoreria_type='efectivo')
        standard = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner.id,
            'amount': 100.0,
            'journal_id': self.journal_bank.id,
        })
        self.assertEqual(
            cheque.get_formview_id(),
            self.env.ref('kenocia_tesoreria_v18.view_kenocia_payment_cheque_form').id,
        )
        self.assertEqual(
            transfer.get_formview_id(),
            self.env.ref('kenocia_tesoreria_v18.view_kenocia_payment_transfer_form').id,
        )
        self.assertEqual(
            cash.get_formview_id(),
            self.env.ref('kenocia_tesoreria_v18.view_kenocia_payment_cash_form').id,
        )
        self.assertNotEqual(
            standard.get_formview_id(),
            self.env.ref('kenocia_tesoreria_v18.view_kenocia_payment_cheque_form').id,
        )

    def test_payment_receipt_report_values(self):
        """Recibo de pago incluye contacto y documentos conciliados."""
        payable = self.env['account.account'].search([
            ('account_type', '=', 'liability_payable'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        vendor = self.partner
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': vendor.id,
            'invoice_date': '2026-01-15',
            'date': '2026-01-15',
            'invoice_line_ids': [(0, 0, {
                'name': 'Servicio test recibo',
                'quantity': 1,
                'price_unit': 500.0,
            })],
        })
        bill.action_post()
        bill_line = bill.line_ids.filtered(
            lambda line: line.account_id == payable,
        )[:1]

        payment = self._create_treasury_payment(
            amount=500.0,
            tesoreria_type=False,
        )
        payment.action_post()
        pay_line = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == payable and not line.reconciled,
        )[:1]
        self.env['account.partial.reconcile'].create({
            'debit_move_id': pay_line.id,
            'credit_move_id': bill_line.id,
            'amount': 500.0,
            'debit_amount_currency': 500.0,
            'credit_amount_currency': 500.0,
        })

        values = payment._get_payment_receipt_report_values()
        self.assertEqual(values['receipt_partner'], vendor)
        self.assertEqual(len(values['receipt_documents']), 1)
        self.assertEqual(values['receipt_documents'][0]['move'], bill)
        self.assertEqual(values['receipt_documents'][0]['amount'], 500.0)
        self.assertTrue(values['display_invoices'])
