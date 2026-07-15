# Copyright 2026 Kenocia
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _risk_amount_in_currency(self):
        """Untaxed/total order amount converted to the partner risk currency."""
        self.ensure_one()
        risk_currency = self.partner_id.commercial_partner_id.risk_currency_id
        if not risk_currency or self.currency_id == risk_currency:
            return self.amount_total
        return self.currency_id._convert(
            self.amount_total,
            risk_currency,
            self.company_id,
            self.date_order or fields.Date.context_today(self),
            round=False,
        )

    def _check_financial_risk(self):
        """Return the risk-exceeded wizard action when the order would exceed
        the customer credit limit, otherwise ``False``."""
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        if not partner.financial_risk_enabled:
            return False
        credit_limit = partner.sudo().credit_limit
        if not credit_limit:
            return False
        order_amount = self._risk_amount_in_currency()
        if (
            not partner.risk_exception
            and (partner.risk_total + order_amount) <= credit_limit
        ):
            return False
        risk_msg = partner._get_risk_exceeded_html(
            order_amount, self.env._("sale order")
        )
        return (
            self.env["partner.risk.exceeded.wiz"]
            .create(
                {
                    "exception_msg": risk_msg,
                    "partner_id": partner.id,
                    "origin_reference": "{},{}".format("sale.order", self.id),
                    "continue_method": "action_confirm",
                }
            )
            .action_show()
        )

    def action_confirm(self):
        if not self.env.context.get("bypass_risk", False):
            for order in self:
                wiz_action = order._check_financial_risk()
                if wiz_action:
                    return wiz_action
        return super().action_confirm()
