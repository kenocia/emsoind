# -*- coding: utf-8 -*-

from odoo import api, models


class ReportInvoiceSar(models.AbstractModel):
    _name = 'report.kc_fiscal_hn_v18.id_report_invoice_sar'
    _description = 'Reporte Factura SAR Honduras'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        docs = self.env['account.move'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'account.move',
            'docs': docs,
            'sar_print_labels': data.get('sar_print_labels') or {},
        }
