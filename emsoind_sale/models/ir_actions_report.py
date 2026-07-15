# -*- coding: utf-8 -*-

from odoo import models

_PRODUCTION_ORDER_REPORT = 'emsoind_sale.report_sale_production_order'


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)
        if report.report_name == _PRODUCTION_ORDER_REPORT and res_ids:
            ids = [res_ids] if isinstance(res_ids, int) else list(res_ids)
            self.env['sale.order'].browse(ids)._emsoind_check_production_report_allowed()
        return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
