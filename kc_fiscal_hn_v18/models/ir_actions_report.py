# -*- coding: utf-8 -*-

from odoo import models

_SAR_PRINT_CONTROLLED_REPORTS = frozenset([
    'kc_fiscal_hn_v18.id_report_invoice_sar',
])

_PROFORMA_REPORT = 'kc_fiscal_hn_v18.report_sale_proforma'


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _sar_print_prepare_pending(self, report, res_ids, data):
        """Inyecta etiquetas prospectivas en data; devuelve commits pendientes."""
        pending = []
        labels = {}
        Model = self.env[report.model]
        for res_id in set(res_ids):
            record = Model.browse(res_id)
            if not record.exists() or not hasattr(record, '_sar_print_prepare_render'):
                continue
            info = record._sar_print_prepare_render(report)
            if not info:
                continue
            pending.append(info)
            labels[res_id] = info['label']
        if labels:
            data['sar_print_labels'] = labels
        return pending

    def _sar_print_commit_pending(self, report, pending):
        for info in pending:
            record = self.env[info['res_model']].browse(info['res_id'])
            if not record.exists():
                continue
            record._register_sar_print(
                report,
                info['prospective_number'],
                info['print_type'],
                clear_reissue=info.get('clear_reissue', False),
            )

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        data = dict(data or {})
        pending = []
        report = None

        if res_ids:
            if isinstance(res_ids, int):
                res_ids = [res_ids]
            res_ids = list(set(res_ids))
            report = self._get_report(report_ref)
            if report.report_name == _PROFORMA_REPORT:
                self.env['sale.order'].browse(res_ids)._check_proforma_report_allowed()
            if report.report_name in _SAR_PRINT_CONTROLLED_REPORTS:
                pending = self._sar_print_prepare_pending(
                    report, res_ids, data,
                )

        try:
            result = super()._render_qweb_pdf(
                report_ref, res_ids=res_ids, data=data,
            )
        except Exception:
            raise
        else:
            if pending and report:
                self._sar_print_commit_pending(report, pending)
            return result
