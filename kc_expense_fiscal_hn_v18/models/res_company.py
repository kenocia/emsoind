# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    kc_expense_reimbursement_account_id = fields.Many2one(
        'account.account',
        string='Cuenta reembolso empleados (gastos)',
        check_company=True,
        domain="[('account_type', '=', 'liability_payable'), ('deprecated', '=', False)]",
        help='Cuenta por pagar usada al aplicar gastos sin anticipo o por el '
             'excedente cuando el anticipo no alcanza.',
    )
    kc_expense_fund_journal_id = fields.Many2one(
        'account.journal',
        string='Diario aplicación fondo gastos',
        check_company=True,
        domain="[('type', '=', 'general')]",
        help='Diario para el asiento interno que cancela CxP proveedor contra '
             'anticipo o reembolso del empleado.',
    )
