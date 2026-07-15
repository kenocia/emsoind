# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = "account.payment"

    old_name = fields.Char(
        string='Nombre Anterior',
        help='Nombre anterior del pago'
    )
    
