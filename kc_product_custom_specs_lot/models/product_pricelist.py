# -*- coding: utf-8 -*-

from odoo import models


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    def _compute_price_rule(
            self, products, quantity, currency=None, uom=None, date=False,
            compute_price=True, **kwargs
    ):
        technical_key = kwargs.pop('technical_key', None)
        if technical_key is not None:
            return super(ProductPricelist, self.with_context(
                kc_technical_key=technical_key,
            ))._compute_price_rule(
                products,
                quantity,
                currency=currency,
                uom=uom,
                date=date,
                compute_price=compute_price,
                **kwargs,
            )
        return super()._compute_price_rule(
            products,
            quantity,
            currency=currency,
            uom=uom,
            date=date,
            compute_price=compute_price,
            **kwargs,
        )
