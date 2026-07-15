# -*- coding: utf-8 -*-

from odoo import api, models


class AccountMoveSend(models.AbstractModel):
    _inherit = 'account.move.send'

    @api.model
    def _get_default_pdf_report_id(self, move):
        """Botón Imprimir / Enviar: usar reporte SAR según diario fiscal."""
        sar_report = move._get_fiscal_sar_pdf_report()
        if sar_report:
            return sar_report
        return super()._get_default_pdf_report_id(move)
