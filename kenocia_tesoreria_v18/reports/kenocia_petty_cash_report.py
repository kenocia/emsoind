# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import api, models


class ReportPettyCashOperational(models.AbstractModel):
    _name = 'report.kenocia_tesoreria_v18.report_petty_cash_operational'
    _description = 'Reporte operativo caja chica'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['kenocia.petty.cash.report.wizard'].browse(docids)
        report_data = (data or {}).get('report_data')
        if not report_data and wizard:
            report_data = wizard._get_report_data()
        return {
            'doc_ids': docids,
            'doc_model': 'kenocia.petty.cash.report.wizard',
            'docs': wizard,
            'data': report_data or {},
        }


class ReportPettyCashFiscal(models.AbstractModel):
    _name = 'report.kenocia_tesoreria_v18.report_petty_cash_fiscal'
    _description = 'Reporte fiscal SAR caja chica'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['kenocia.petty.cash.report.wizard'].browse(docids)
        report_data = (data or {}).get('report_data')
        if not report_data and wizard:
            report_data = wizard._get_fiscal_data()
        return {
            'doc_ids': docids,
            'doc_model': 'kenocia.petty.cash.report.wizard',
            'docs': wizard,
            'data': report_data or {},
        }
