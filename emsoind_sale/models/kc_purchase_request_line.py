# -*- coding: utf-8 -*-

from odoo import fields, models


class KcPurchaseRequestLine(models.Model):
    _inherit = 'kc.purchase.request.line'

    vendor_id = fields.Many2one(
        domain=lambda self: self.env['res.partner'].EMSOIND_SUPPLIER_DOMAIN,
    )
