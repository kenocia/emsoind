# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestKenociaRolesAndReports(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_cxc = cls.env.ref('kenocia_tesoreria_v18.group_tesoreria_cxc')
        cls.group_cxp = cls.env.ref('kenocia_tesoreria_v18.group_tesoreria_cxp')
        cls.group_admin = cls.env.ref('kenocia_tesoreria_v18.group_tesoreria_admin')

        cls.env.ref('base.user_admin').write({
            'group_ids': [(4, cls.group_admin.id)],
        })
        cls.admin_user = cls.env.ref('base.user_admin')
        cls.env = cls.env(user=cls.admin_user)

        cls.user_cxc = cls.env['res.users'].create({
            'name': 'Usuario CXC Test',
            'login': 'tesoreria_cxc_test',
            'group_ids': [
                (6, 0, [
                    cls.env.ref('base.group_user').id,
                    cls.group_cxc.id,
                ]),
            ],
        })
        cls.user_cxp = cls.env['res.users'].create({
            'name': 'Usuario CXP Test',
            'login': 'tesoreria_cxp_test',
            'group_ids': [
                (6, 0, [
                    cls.env.ref('base.group_user').id,
                    cls.group_cxp.id,
                ]),
            ],
        })

        cls.partner_customer = cls.env['res.partner'].create({
            'name': 'Cliente Roles Test',
            'customer_rank': 1,
        })
        cls.partner_supplier = cls.env['res.partner'].create({
            'name': 'Proveedor Roles Test',
            'supplier_rank': 1,
        })
        cls.journal_bank = cls.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)
        if not cls.journal_bank:
            cls.journal_bank = cls.env['account.journal'].create({
                'name': 'Banco Roles Test',
                'type': 'bank',
                'code': 'KTRL',
            })

        cls.advance_account_cxc = cls.env['account.account'].create({
            'name': 'Anticipos Clientes Roles Test',
            'code': '209011R',
            'account_type': 'asset_current',
            'reconcile': True,
        })
        cls.advance_account_cxp = cls.env['account.account'].create({
            'name': 'Anticipos Proveedores Roles Test',
            'code': '209012R',
            'account_type': 'asset_current',
            'reconcile': True,
        })
        cls.env.company.write({
            'kenocia_advance_account_cxc_id': cls.advance_account_cxc.id,
            'kenocia_advance_account_cxp_id': cls.advance_account_cxp.id,
        })

    def test_role_cxc_cannot_create_supplier_advance(self):
        """TEST-17: rol CXC no puede crear adelantos de proveedor."""
        Advance = self.env['kenocia.advance.payment'].with_user(self.user_cxc)
        with self.assertRaises(AccessError):
            Advance.create({
                'advance_type': 'supplier',
                'partner_id': self.partner_supplier.id,
                'journal_id': self.journal_bank.id,
                'amount': 1000,
                'date': '2026-06-02',
            })

    def test_role_cxp_cannot_create_customer_advance(self):
        """TEST-17b: rol CXP no puede crear adelantos de cliente."""
        Advance = self.env['kenocia.advance.payment'].with_user(self.user_cxp)
        with self.assertRaises(AccessError):
            Advance.create({
                'advance_type': 'customer',
                'partner_id': self.partner_customer.id,
                'journal_id': self.journal_bank.id,
                'amount': 1000,
                'date': '2026-06-02',
            })

    def test_role_cxc_cannot_create_outbound_payment(self):
        """TEST-17c: rol CXC no puede crear pagos salientes."""
        Payment = self.env['account.payment'].with_user(self.user_cxc)
        with self.assertRaises(AccessError):
            Payment.create({
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'partner_id': self.partner_supplier.id,
                'amount': 500,
                'journal_id': self.journal_bank.id,
            })

    def test_record_rule_cxc_hides_supplier_advances(self):
        """TEST-17d: reglas de registro ocultan adelantos CXP al rol CXC."""
        supplier_advance = self.env['kenocia.advance.payment'].create({
            'advance_type': 'supplier',
            'partner_id': self.partner_supplier.id,
            'journal_id': self.journal_bank.id,
            'amount': 2500,
            'date': '2026-06-02',
        })
        visible = self.env['kenocia.advance.payment'].with_user(
            self.user_cxc,
        ).search([('id', '=', supplier_advance.id)])
        self.assertFalse(visible)

    def test_advance_amount_tracking(self):
        """TEST-16: campos de negocio con tracking y mensajes en chatter."""
        Advance = self.env['kenocia.advance.payment']
        for field_name in ('amount', 'state', 'partner_id', 'advance_type', 'date'):
            self.assertTrue(
                Advance._fields[field_name].tracking,
                f'{field_name} debe tener tracking=True',
            )
        advance = Advance.create({
            'advance_type': 'customer',
            'partner_id': self.partner_customer.id,
            'journal_id': self.journal_bank.id,
            'amount': 10000,
            'date': '2026-06-02',
        })
        self.assertTrue(advance.message_ids)

    def test_report_wizard_csv_export(self):
        """TEST-18: wizard exporta CSV con adelantos del período."""
        self.env['kenocia.advance.payment'].create({
            'advance_type': 'customer',
            'partner_id': self.partner_customer.id,
            'journal_id': self.journal_bank.id,
            'amount': 3000,
            'date': '2026-06-02',
        })
        wizard = self.env['kenocia.report.wizard'].create({
            'report_type': 'advances',
            'date_from': '2026-06-01',
            'date_to': '2026-06-30',
            'advance_type': 'customer',
        })
        action = wizard.action_export_csv()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        attachment_id = int(action['url'].split('/web/content/')[1].split('?')[0])
        attachment = self.env['ir.attachment'].browse(attachment_id)
        self.assertTrue(attachment.datas)
        self.assertIn('tesoreria_adelantos', attachment.name)

    def test_report_wizard_pdf_action(self):
        """TEST-19: wizard genera acción PDF para adelantos."""
        advance = self.env['kenocia.advance.payment'].create({
            'advance_type': 'customer',
            'partner_id': self.partner_customer.id,
            'journal_id': self.journal_bank.id,
            'amount': 4500,
            'date': '2026-06-02',
        })
        wizard = self.env['kenocia.report.wizard'].create({
            'report_type': 'advances',
            'date_from': '2026-06-01',
            'date_to': '2026-06-30',
        })
        action = wizard.action_print_pdf()
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertIn(advance.id, action['context']['active_ids'])
        self.assertEqual(
            action['report_name'],
            'kenocia_tesoreria_v18.report_advance_receipt',
        )
