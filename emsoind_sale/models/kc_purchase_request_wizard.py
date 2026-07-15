# -*- coding: utf-8 -*-

from odoo import fields, models


class KcPurchaseRequestLineMakePo(models.TransientModel):
    _inherit = 'kc.purchase.request.line.make.po'

    partner_id = fields.Many2one(
        domain=lambda self: self.env['res.partner'].EMSOIND_SUPPLIER_DOMAIN,
    )


class KcPurchaseRequestMergeRfq(models.TransientModel):
    _inherit = 'kc.purchase.request.merge.rfq'

    partner_id = fields.Many2one(
        domain=lambda self: self.env['res.partner'].EMSOIND_SUPPLIER_DOMAIN,
    )
