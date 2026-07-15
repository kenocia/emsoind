# -*- coding: utf-8 -*-

import base64
import io
import logging

import xlsxwriter
from odoo import fields, models, _
from odoo.exceptions import ValidationError

from ..models.fiscal_book_mixin import BOOK_ESTADO

_logger = logging.getLogger(__name__)


class ReportExemptionsSAR(models.TransientModel):
    _name = 'kc_fiscal_hn.wizard.exemptions_sar'
    _description = 'Reporte de Exenciones y Exoneraciones SAR'
    _inherit = ['kc.fiscal.report.source.mixin']

    date_from = fields.Date(string='Fecha Desde', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Fecha Hasta', required=True, default=fields.Date.today)
    company_id = fields.Many2one(
        'res.company', string='Compañía', default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', default=lambda self: self.env.company.currency_id,
    )
    exemption_type = fields.Selection([
        ('all', 'Todas las Exenciones'),
        ('exempt', 'Exento'),
        ('exonerated', 'Exonerado'),
    ], string='Tipo de Exención', default='all', required=True)
    book_period_label = fields.Char(
        string='Libro / Período',
        compute='_compute_fiscal_book_display',
    )

    excel_file = fields.Binary(string='Archivo Excel', readonly=True)
    excel_filename = fields.Char(string='Nombre del Archivo', readonly=True)
    total_invoices = fields.Integer(string='Total Facturas', readonly=True)
    total_exempt = fields.Monetary(
        string='Monto Exento Total', readonly=True, currency_field='currency_id',
    )
    total_exonerated = fields.Monetary(
        string='Monto Exonerado Total', readonly=True, currency_field='currency_id',
    )

    def _fiscal_report_book_model(self):
        return 'kc_fiscal_hn.book.exemptions'

    def _fiscal_report_book_kind(self):
        return 'flat'

    def _fiscal_report_selected_book(self):
        if self.data_source != 'book':
            return self.env['kc_fiscal_hn.book.exemptions'].browse()
        return self._search_books_for_period()

    def _rows_from_book_lines(self, lines):
        estado_labels = dict(BOOK_ESTADO)
        rows = []
        for line in lines:
            move = line.move_id
            rows.append({
                'name': line.numero_factura or 'N/A',
                'date': line.fecha,
                'partner_name': line.cliente or 'N/A',
                'partner_vat': line.rtn_cliente or 'N/A',
                'doc_type': _('Exonerado'),
                'amount_exento': 0,
                'amount_exonerado': line.monto_exonerado or 0,
                'amount_total': line.total_factura or 0,
                'cai': move.cai if move else 'N/A',
                'state_label': estado_labels.get(line.estado, line.estado or ''),
                'move': move,
            })
        return rows

    def _rows_from_live_invoices(self, invoices):
        state_labels = dict(self.env['account.move']._fields['state'].selection)
        move_type_labels = dict(self.env['account.move']._fields['move_type'].selection)
        rows = []
        for invoice in invoices:
            rows.append({
                'name': invoice.name or 'N/A',
                'date': invoice.date,
                'partner_name': invoice.commercial_partner_id.name or 'N/A',
                'partner_vat': invoice.commercial_partner_id.vat or 'N/A',
                'doc_type': move_type_labels.get(invoice.move_type, invoice.move_type),
                'amount_exento': invoice.amount_exento or 0,
                'amount_exonerado': invoice.amount_exonerado or 0,
                'amount_total': invoice.amount_total or 0,
                'cai': invoice.cai or invoice.cai_proveedor or 'N/A',
                'state_label': state_labels.get(invoice.state, invoice.state),
                'move': invoice,
            })
        return rows

    def _get_exemption_rows(self):
        self.ensure_one()
        if self.data_source == 'book':
            if self.exemption_type == 'exempt':
                raise ValidationError(_(
                    'El libro de exoneraciones no incluye ventas exentas. '
                    'Use «Facturas en vivo» para ese filtro.',
                ))
            self._validate_fiscal_report_source()
            lines = self._fiscal_report_selected_book()
            if not lines:
                raise ValidationError(_(
                    'No hay líneas de exoneraciones en el libro para el período.',
                ))
            return self._rows_from_book_lines(lines)

        invoices = self.get_exemptions()
        if not invoices:
            raise ValidationError(_(
                'No se encontraron facturas con exenciones en vivo para el '
                'período y estado seleccionados.',
            ))
        return self._rows_from_live_invoices(invoices)

    def action_generate_report(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise ValidationError(_('La fecha desde no puede ser mayor a la fecha hasta'))
        rows = self._get_exemption_rows()
        self.total_invoices = len(rows)
        self.total_exempt = sum(r['amount_exento'] for r in rows)
        self.total_exonerated = sum(r['amount_exonerado'] for r in rows)
        return self.print_report(rows)

    def print_report(self, rows=None):
        if rows is None:
            rows = self._get_exemption_rows()
        source_label = self._fiscal_source_label_for_excel()
        filename = f'Reporte_Exenciones_SAR_{self.date_from}_{self.date_to}.xlsx'
        stream = io.BytesIO()
        workbook = xlsxwriter.Workbook(stream, {'in_memory': True})
        encabezado = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        titulos = workbook.add_format({'bold': True, 'align': 'center'})
        subtitulos = workbook.add_format({'bold': True, 'align': 'center', 'text_wrap': True})
        detalle = workbook.add_format({})
        detalle_moneda = workbook.add_format({'num_format': 'L#,##0.00'})

        sheet = workbook.add_worksheet('Resumen General')
        sheet.merge_range(
            0, 0, 0, 5,
            'REPORTE DE EXENCIONES Y EXONERACIONES SAR - HONDURAS',
            encabezado,
        )
        sheet.merge_range(1, 0, 1, 5, f'Período: {self.date_from} - {self.date_to}', subtitulos)
        sheet.merge_range(2, 0, 2, 5, source_label, subtitulos)

        sheet.write(4, 0, 'Empresa:', titulos)
        sheet.write(4, 1, self.company_id.name, detalle)
        sheet.write(5, 0, 'RTN:', titulos)
        sheet.write(5, 1, self.company_id.vat or 'N/A', detalle)

        sheet.write(7, 0, 'TOTALES GENERALES', encabezado)
        sheet.write(8, 0, 'Total Facturas', detalle)
        sheet.write(8, 1, len(rows), detalle)
        sheet.write(9, 0, 'Monto Exento Total', detalle)
        sheet.write(9, 2, sum(r['amount_exento'] for r in rows), detalle_moneda)
        sheet.write(10, 0, 'Monto Exonerado Total', detalle)
        sheet.write(10, 2, sum(r['amount_exonerado'] for r in rows), detalle_moneda)

        sheet_detail = workbook.add_worksheet('Detalle por Factura')
        headers = [
            'Número Factura', 'Fecha', 'Cliente/Proveedor', 'RTN', 'Tipo Documento',
            'Monto Exento', 'Monto Exonerado', 'Total Factura', 'CAI', 'Estado',
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
            sheet_detail.write(row_idx, 4, row['doc_type'], detalle)
            sheet_detail.write(row_idx, 5, row['amount_exento'], detalle_moneda)
            sheet_detail.write(row_idx, 6, row['amount_exonerado'], detalle_moneda)
            sheet_detail.write(row_idx, 7, row['amount_total'], detalle_moneda)
            sheet_detail.write(row_idx, 8, row['cai'], detalle)
            sheet_detail.write(row_idx, 9, row['state_label'], detalle)
            row_idx += 1

        sheet_summary = workbook.add_worksheet('Resumen por Tipo')
        summary_headers = [
            'Tipo de Exención', 'Cantidad Facturas', 'Monto Total',
            'Promedio por Factura',
        ]
        for col, header in enumerate(summary_headers):
            sheet_summary.write(0, col, header, titulos)

        exempt_rows = [r for r in rows if r['amount_exento'] > 0]
        exonerated_rows = [r for r in rows if r['amount_exonerado'] > 0]
        exemption_summary = {
            'Exento': {
                'count': len(exempt_rows),
                'amount': sum(r['amount_exento'] for r in exempt_rows),
            },
            'Exonerado': {
                'count': len(exonerated_rows),
                'amount': sum(r['amount_exonerado'] for r in exonerated_rows),
            },
        }
        row_idx = 1
        for exemption_type, data in exemption_summary.items():
            avg = data['amount'] / data['count'] if data['count'] else 0
            sheet_summary.write(row_idx, 0, exemption_type, detalle)
            sheet_summary.write(row_idx, 1, data['count'], detalle)
            sheet_summary.write(row_idx, 2, data['amount'], detalle_moneda)
            sheet_summary.write(row_idx, 3, avg, detalle_moneda)
            row_idx += 1

        sheet_products = workbook.add_worksheet('Productos Exentos/Exonerados')
        product_headers = [
            'Factura', 'Fecha', 'Producto', 'Cantidad', 'Precio Unitario',
            'Subtotal', 'Tipo Exención', 'Monto Exento/Exonerado',
        ]
        for col, header in enumerate(product_headers):
            sheet_products.write(0, col, header, titulos)

        row_idx = 1
        for row in rows:
            invoice = row.get('move')
            if not invoice:
                continue
            for line in invoice.invoice_line_ids:
                has_exempt_tax = any(
                    tax.tax_group_id.name == 'Exento' for tax in line.tax_ids
                )
                has_exonerated_tax = any(
                    tax.tax_group_id.name == 'Exonerado' for tax in line.tax_ids
                )
                if not has_exempt_tax and not has_exonerated_tax:
                    continue
                exemption_type = 'Exento' if has_exempt_tax else 'Exonerado'
                sheet_products.write(row_idx, 0, row['name'], detalle)
                sheet_products.write(
                    row_idx, 1,
                    row['date'].strftime('%d/%m/%Y') if row['date'] else 'N/A',
                    detalle,
                )
                sheet_products.write(row_idx, 2, line.product_id.name or 'N/A', detalle)
                sheet_products.write(row_idx, 3, line.quantity, detalle)
                sheet_products.write(row_idx, 4, line.price_unit, detalle_moneda)
                sheet_products.write(row_idx, 5, line.price_subtotal, detalle_moneda)
                sheet_products.write(row_idx, 6, exemption_type, detalle)
                sheet_products.write(row_idx, 7, line.price_subtotal, detalle_moneda)
                row_idx += 1

        workbook.close()
        export_id = self.env['kc_fiscal_hn.exemptions_sar.excel'].create({
            'excel_file': base64.b64encode(stream.getvalue()),
            'file_name': filename,
        })
        stream.close()
        return {
            'view_mode': 'form',
            'res_id': export_id.id,
            'res_model': 'kc_fiscal_hn.exemptions_sar.excel',
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def get_exemptions(self):
        domain = [
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]
        domain.extend(self._live_move_state_domain())
        if self.exemption_type == 'exempt':
            domain.append(('amount_exento', '>', 0))
        elif self.exemption_type == 'exonerated':
            domain.append(('amount_exonerado', '>', 0))
        else:
            domain.extend(['|', ('amount_exento', '>', 0), ('amount_exonerado', '>', 0)])
        return self.env['account.move'].search(domain)
    
    def action_download_excel(self):
        """Descargar archivo Excel"""
        if not self.excel_file:
            raise ValidationError(_('Primero debe generar el reporte'))
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=excel_file&filename_field=excel_filename&download=true',
            'target': 'self',
        }


class ReportExemptionsSarExcel(models.TransientModel):
    _name = 'kc_fiscal_hn.exemptions_sar.excel'
    _description = 'Reporte de Exenciones SAR Excel'

    excel_file = fields.Binary('Archivo Excel', readonly=True)
    file_name = fields.Char('Nombre del Archivo', size=64)
    
    def action_download_excel(self):
        """Descargar archivo Excel"""
        if not self.excel_file:
            raise ValidationError(_('Primero debe generar el reporte'))
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=excel_file&filename_field=excel_filename&download=true',
            'target': 'self',
        } 