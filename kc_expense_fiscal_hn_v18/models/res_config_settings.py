# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kc_expense_reimbursement_account_id = fields.Many2one(
        related='company_id.kc_expense_reimbursement_account_id',
        readonly=False,
    )
    kc_expense_fund_journal_id = fields.Many2one(
        related='company_id.kc_expense_fund_journal_id',
        readonly=False,
    )
