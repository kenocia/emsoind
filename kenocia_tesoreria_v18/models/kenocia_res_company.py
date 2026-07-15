# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    kenocia_advance_account_cxc_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta anticipos clientes (CXC)',
        domain="[('account_type', 'in', ('liability_current', 'liability_payable'))]",
        help='Cuenta contable de PASIVO para registrar anticipos de clientes '
             '(ej. 2090101 Anticipos de clientes). El cliente paga por adelantado '
             'y la empresa queda con la obligación de entregar el bien/servicio.',
    )
    kenocia_advance_account_cxp_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta anticipos proveedores (CXP)',
        domain="[('account_type', 'in', ('asset_current', 'asset_receivable', 'asset_prepayments'))]",
        help='Cuenta contable para registrar pagos anticipados a proveedores.',
    )

    def action_kenocia_open_bank_accounts(self):
        self.ensure_one()
        return self.env['account.account'].action_kenocia_open_bank_cash_accounts()

    def action_kenocia_open_advance_accounts(self):
        self.ensure_one()
        return self.env['account.account'].action_kenocia_open_advance_accounts()
