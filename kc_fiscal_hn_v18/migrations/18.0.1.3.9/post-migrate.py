# -*- coding: utf-8 -*-

def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    from odoo.addons.kc_fiscal_hn_v18.hooks import (
        configure_account_move_company_journal_defaults,
        remove_account_move_journal_ir_default,
    )

    env = api.Environment(cr, SUPERUSER_ID, {})
    remove_account_move_journal_ir_default(env)
    configure_account_move_company_journal_defaults(env)
