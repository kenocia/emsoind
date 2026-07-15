# -*- coding: utf-8 -*-

from odoo import models


class AccountMoveSarPrintControl(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'kc_fiscal_hn.print.control.mixin']
