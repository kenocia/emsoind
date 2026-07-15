# -*- coding: utf-8 -*-

import base64
import io
import logging

import xlsxwriter
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ReportSalesSAR(models.TransientModel):
    _name = 'kc_fiscal_hn.wizard.sales_sar'
    _description = 'Reporte de Ventas SAR'
    _inherit = ['kc.fiscal.report.source.mixin']

    date_from = fields.Date(string='Fecha Desde', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Fecha Hasta', required=True, default=fields.Date.today)
    company_id = fields.Many2one(
        'res.company', string='Compañía', default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', default=lambda self: self.env.company.currency_id,
    )
    book_sales_id = fields.Many2one(
        'kc_fiscal_hn.book.sales',
        string='Libro / Declaración',
    )
    available_book_sales_ids = fields.Many2many(
        'kc_fiscal_hn.book.sales',
        compute='_compute_available_book_sales_ids',
    )
    book_period_label = fields.Char(
        string='Libro / Período',
        compute='_compute_fiscal_book_display',
    )

    @api.depends('company_id')
    def _compute_available_book_sales_ids(self):
        for wizard in self:
            wizard.available_book_sales_ids = wizard._search_books_for_period()

    @api.onchange('book_sales_id')
    def _onchange_book_sales_id(self):
        self._compute_fiscal_book_display()

    group_by_tax_rate = fields.Boolean(string='Agrupar por Tasa de Impuesto', default=True)
    group_by_customer_type = fields.Boolean(string='Agrupar por Tipo de Cliente', default=True)

    excel_file = fields.Binary(string='Archivo Excel', readonly=True)
    excel_filename = fields.Char(string='Nombre del Archivo', readonly=True)
    total_invoices = fields.Integer(string='Total Facturas', readonly=True)
    total_amount = fields.Monetary(
        string='Monto Total', readonly=True, currency_field='currency_id',
    )
    total_isv = fields.Monetary(
        string='ISV Total', readonly=True, currency_field='currency_id',
    )
    total_exempt = fields.Monetary(
        string='Exento Total', readonly=True, currency_field='currency_id',
    )
    total_exonerated = fields.Monetary(
        string='Exonerado Total', readonly=True, currency_field='currency_id',
    )

    def _fiscal_report_book_model(self):
        return 'kc_fiscal_hn.book.sales'

    def _fiscal_report_book_kind(self):
        return 'header'

    def _fiscal_report_selected_book(self):
        return self.book_sales_id

    def get_invoices(self):
        """Facturas en vivo para el reporte."""
        domain = [
            ('move_type', '=', 'out_invoice'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]
        domain.extend(self._live_move_state_domain())
        return self.env['account.move'].search(domain)

    def _get_book_sales_lines(self):
        self._validate_fiscal_report_source()
        return self.book_sales_id.line_ids.sorted(
            key=lambda line: (line.fecha or '', line.numero_factura or ''),
        )

    def _rows_from_live_invoices(self, invoices):
        state_labels = dict(self.env['account.move']._fields['state'].selection)
        rows = []
        for invoice in invoices:
            rows.append({
                'name': invoice.name or 'N/A',
                'date': invoice.invoice_date or invoice.date,
                'partner_name': invoice.commercial_partner_id.name or 'N/A',
                'partner_vat': invoice.commercial_partner_id.vat or 'N/A',
                'base_imponible': invoice.base_imponible_total or 0,
                'amount_isv15': invoice.amount_isv15 or 0,
                'gravado_isv15': invoice.gravado_isv15 or 0,
                'amount_isv18': invoice.amount_isv18 or 0,
                'gravado_isv18': invoice.gravado_isv18 or 0,
                'amount_exento': invoice.amount_exento or 0,
                'amount_exonerado': invoice.amount_exonerado or 0,
                'amount_discount': invoice.amount_discount or 0,
                'amount_total': invoice.amount_total or 0,
                'isv_total': invoice.isv_total or 0,
                'cai': invoice.cai or 'N/A',
                'state_label': state_labels.get(invoice.state, invoice.state),
            })
        return rows

    def _rows_from_book_lines(self, lines):
        rows = []
        for line in lines:
            if line.es_anulada:
                state_label = _('Anulada')
            else:
                state_label = _('Confirmada')
            base = (line.gravado_15 or 0) + (line.gravado_18 or 0)
            rows.append({
                'name': line.numero_factura or 'N/A',
                'date': line.fecha,
                'partner_name': line.cliente or 'N/A',
                'partner_vat': line.rtn_cliente or 'N/A',
                'base_imponible': base,
                'amount_isv15': line.isv_15 or 0,
                'gravado_isv15': line.gravado_15 or 0,
                'amount_isv18': line.isv_18 or 0,
                'gravado_isv18': line.gravado_18 or 0,
                'amount_exento': line.exento or 0,
                'amount_exonerado': line.exonerado or 0,
                'amount_discount': line.descuento or 0,
                'amount_total': line.amount_total or 0,
                'isv_total': (line.isv_15 or 0) + (line.isv_18 or 0),
                'cai': line.cai or 'N/A',
                'state_label': state_label,
            })
        return rows

    def _get_report_rows(self):
        self.ensure_one()
        if self.data_source == 'book':
            lines = self._get_book_sales_lines()
            if not lines:
                raise ValidationError(_(
                    'El libro seleccionado no tiene líneas para exportar.',
                ))
            return self._rows_from_book_lines(lines)
        invoices = self.get_invoices()
        if not invoices:
            raise ValidationError(_(
                'No se encontraron facturas en vivo para el período y '
                'estado de documentos seleccionados.',
            ))
        return self._rows_from_live_invoices(invoices)

    def print_report(self):
        self.ensure_one()
        rows = self._get_report_rows()
        source_label = self._fiscal_source_label_for_excel()
        filename = f'Reporte_Ventas_SAR_{self.date_from}_{self.date_to}.xlsx'
        stream = io.BytesIO()
        workbook = xlsxwriter.Workbook(stream, {'in_memory': True})
        encabezado = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        titulos = workbook.add_format({'bold': True, 'align': 'center'})
        subtitulos = workbook.add_format({'bold': True, 'align': 'center', 'text_wrap': True})
        detalle = workbook.add_format({})
        detalle_moneda = workbook.add_format({'num_format': 'L#,##0.00'})

        sheet = workbook.add_worksheet('Resumen General')
        sheet.merge_range(0, 0, 0, 5, 'REPORTE DE VENTAS SAR - HONDURAS', encabezado)
        sheet.merge_range(1, 0, 1, 5, f'Período: {self.date_from} - {self.date_to}', subtitulos)
        sheet.merge_range(2, 0, 2, 5, source_label, subtitulos)

        sheet.write(4, 0, 'Empresa:', titulos)
        sheet.write(4, 1, self.company_id.name, detalle)
        sheet.write(5, 0, 'RTN:', titulos)
        sheet.write(5, 1, self.company_id.vat or 'N/A', detalle)

        sheet.write(7, 0, 'TOTALES GENERALES', encabezado)
        sheet.write(8, 0, 'Concepto', titulos)
        sheet.write(8, 1, 'Cantidad', titulos)
        sheet.write(8, 2, 'Monto', titulos)

        sheet.write(9, 0, 'Total Facturas', detalle)
        sheet.write(9, 1, len(rows), detalle)
        sheet.write(9, 2, sum(r['amount_total'] for r in rows), detalle_moneda)
        sheet.write(10, 0, 'ISV Total', detalle)
        sheet.write(10, 2, sum(r['isv_total'] for r in rows), detalle_moneda)
        sheet.write(11, 0, 'Exento Total', detalle)
        sheet.write(11, 2, sum(r['amount_exento'] for r in rows), detalle_moneda)
        sheet.write(12, 0, 'Exonerado Total', detalle)
        sheet.write(12, 2, sum(r['amount_exonerado'] for r in rows), detalle_moneda)

        sheet_detail = workbook.add_worksheet('Detalle por Factura')
        headers = [
            'Número Factura', 'Fecha', 'Cliente', 'RTN Cliente', 'Base Imponible',
            'ISV 15%', 'Base 15%', 'ISV 18%', 'Base 18%', 'Exento', 'Exonerado',
            'Descuento', 'Total', 'CAI', 'Estado',
        ]
        for col, header in enumerate(headers):
            sheet_detail.write(0, col, header, titulos)

        row_idx = 1
        for row in rows:
            sheet_detail.write(row_idx, 0, row['name'], detalle)
            date_val = row['date']
            sheet_detail.write(
                row_idx, 1,
                date_val.strftime('%d/%m/%Y') if date_val else 'N/A',
                detalle,
            )
            sheet_detail.write(row_idx, 2, row['partner_name'], detalle)
            sheet_detail.write(row_idx, 3, row['partner_vat'], detalle)
            sheet_detail.write(row_idx, 4, row['base_imponible'], detalle_moneda)
            sheet_detail.write(row_idx, 5, row['amount_isv15'], detalle_moneda)
            sheet_detail.write(row_idx, 6, row['gravado_isv15'], detalle_moneda)
            sheet_detail.write(row_idx, 7, row['amount_isv18'], detalle_moneda)
            sheet_detail.write(row_idx, 8, row['gravado_isv18'], detalle_moneda)
            sheet_detail.write(row_idx, 9, row['amount_exento'], detalle_moneda)
            sheet_detail.write(row_idx, 10, row['amount_exonerado'], detalle_moneda)
            sheet_detail.write(row_idx, 11, row['amount_discount'], detalle_moneda)
            sheet_detail.write(row_idx, 12, row['amount_total'], detalle_moneda)
            sheet_detail.write(row_idx, 13, row['cai'], detalle)
            sheet_detail.write(row_idx, 14, row['state_label'], detalle)
            row_idx += 1

        if self.group_by_tax_rate:
            sheet_tax = workbook.add_worksheet('Resumen por Tasa')
            tax_headers = ['Tasa de Impuesto', 'Cantidad Facturas', 'Base Imponible', 'ISV', 'Total']
            for col, header in enumerate(tax_headers):
                sheet_tax.write(0, col, header, titulos)
            tax_summary = {}
            for row in rows:
                if row['amount_isv15'] > 0:
                    tax_summary.setdefault('15%', {'count': 0, 'base': 0, 'tax': 0, 'total': 0})
                    tax_summary['15%']['count'] += 1
                    tax_summary['15%']['base'] += row['gravado_isv15']
                    tax_summary['15%']['tax'] += row['amount_isv15']
                    tax_summary['15%']['total'] += row['gravado_isv15'] + row['amount_isv15']
                if row['amount_isv18'] > 0:
                    tax_summary.setdefault('18%', {'count': 0, 'base': 0, 'tax': 0, 'total': 0})
                    tax_summary['18%']['count'] += 1
                    tax_summary['18%']['base'] += row['gravado_isv18']
                    tax_summary['18%']['tax'] += row['amount_isv18']
                    tax_summary['18%']['total'] += row['gravado_isv18'] + row['amount_isv18']
            row_idx = 1
            for tax_rate, data in tax_summary.items():
                sheet_tax.write(row_idx, 0, tax_rate, detalle)
                sheet_tax.write(row_idx, 1, data['count'], detalle)
                sheet_tax.write(row_idx, 2, data['base'], detalle_moneda)
                sheet_tax.write(row_idx, 3, data['tax'], detalle_moneda)
                sheet_tax.write(row_idx, 4, data['total'], detalle_moneda)
                row_idx += 1

        if self.group_by_customer_type:
            sheet_customer = workbook.add_worksheet('Resumen por Cliente')
            customer_headers = ['Tipo Cliente', 'Cantidad Facturas', 'Base Imponible', 'ISV', 'Total']
            for col, header in enumerate(customer_headers):
                sheet_customer.write(0, col, header, titulos)
            customer_summary = {
                'Con RTN': {'count': 0, 'base': 0, 'tax': 0, 'total': 0},
                'Sin RTN': {'count': 0, 'base': 0, 'tax': 0, 'total': 0},
            }
            for row in rows:
                customer_type = 'Con RTN' if row['partner_vat'] else 'Sin RTN'
                customer_summary[customer_type]['count'] += 1
                customer_summary[customer_type]['base'] += row['base_imponible']
                customer_summary[customer_type]['tax'] += row['isv_total']
                customer_summary[customer_type]['total'] += row['amount_total']
            row_idx = 1
            for customer_type, data in customer_summary.items():
                sheet_customer.write(row_idx, 0, customer_type, detalle)
                sheet_customer.write(row_idx, 1, data['count'], detalle)
                sheet_customer.write(row_idx, 2, data['base'], detalle_moneda)
                sheet_customer.write(row_idx, 3, data['tax'], detalle_moneda)
                sheet_customer.write(row_idx, 4, data['total'], detalle_moneda)
                row_idx += 1

        workbook.close()
        export_id = self.env['kc_fiscal_hn.sales_sar.excel'].create({
            'excel_file': base64.b64encode(stream.getvalue()),
            'file_name': filename,
        })
        stream.close()
        return {
            'view_mode': 'form',
            'res_id': export_id.id,
            'res_model': 'kc_fiscal_hn.sales_sar.excel',
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def action_generate_report(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise ValidationError(_('La fecha desde no puede ser mayor a la fecha hasta'))
        rows = self._get_report_rows()
        self.total_invoices = len(rows)
        self.total_amount = sum(r['amount_total'] for r in rows)
        self.total_isv = sum(r['isv_total'] for r in rows)
        self.total_exempt = sum(r['amount_exento'] for r in rows)
        self.total_exonerated = sum(r['amount_exonerado'] for r in rows)
        return self.print_report()

    def action_download_excel(self):
        if not self.excel_file:
            raise ValidationError(_('Primero debe generar el reporte'))
        return {
            'type': 'ir.actions.act_url',
            'url': (
                f'/web/content/?model={self._name}&id={self.id}'
                f'&field=excel_file&filename_field=excel_filename&download=true'
            ),
            'target': 'self',
        }


class ReportSalesSarExcel(models.TransientModel):
    _name = 'kc_fiscal_hn.sales_sar.excel'
    _description = 'Reporte de Ventas SAR Excel'

    excel_file = fields.Binary('Archivo Excel', readonly=True)
    file_name = fields.Char('Nombre del Archivo', size=64)
