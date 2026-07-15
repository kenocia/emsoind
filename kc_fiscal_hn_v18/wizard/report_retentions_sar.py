# -*- coding: utf-8 -*-

import base64
import io
import logging

import xlsxwriter
from odoo import fields, models, _
from odoo.exceptions import ValidationError

from ..models.fiscal_book_mixin import BOOK_ESTADO

_logger = logging.getLogger(__name__)


class ReportRetentionsSAR(models.TransientModel):
    _name = 'kc_fiscal_hn.wizard.retentions_sar'
    _description = 'Reporte de Retenciones SAR'
    _inherit = ['kc.fiscal.report.source.mixin']

    date_from = fields.Date(string='Fecha Desde', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Fecha Hasta', required=True, default=fields.Date.today)
    company_id = fields.Many2one(
        'res.company', string='Compañía', default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', default=lambda self: self.env.company.currency_id,
    )

    retention_type = fields.Selection([
        ('all', 'Todas las Retenciones'),
        ('isr', 'ISR'),
        ('isv', 'ISV'),
        ('other', 'Otras Retenciones'),
    ], string='Tipo de Retención', default='all', required=True)
    book_period_label = fields.Char(
        string='Libro / Período',
        compute='_compute_fiscal_book_display',
    )

    excel_file = fields.Binary(string='Archivo Excel', readonly=True)
    excel_filename = fields.Char(string='Nombre del Archivo', readonly=True)
    total_retentions = fields.Integer(string='Total Retenciones', readonly=True)
    total_amount = fields.Monetary(
        string='Monto Total Retenido', readonly=True, currency_field='currency_id',
    )
    total_base = fields.Monetary(
        string='Base Imponible Total', readonly=True, currency_field='currency_id',
    )

    def _fiscal_report_book_model(self):
        return 'kc_fiscal_hn.book.retentions'

    def _fiscal_report_book_kind(self):
        return 'flat'

    def _fiscal_report_selected_book(self):
        if self.data_source != 'book':
            return self.env['kc_fiscal_hn.book.retentions'].browse()
        return self._search_books_for_period()

    def _filter_retention_type_book(self, lines):
        if self.retention_type == 'isr':
            return lines.filtered(
                lambda line: line.tipo_retencion
                and 'ISR' in line.tipo_retencion.upper(),
            )
        if self.retention_type == 'isv':
            return lines.filtered(
                lambda line: line.tipo_retencion
                and 'ISV' in line.tipo_retencion.upper(),
            )
        if self.retention_type == 'other':
            return lines.filtered(
                lambda line: line.tipo_retencion
                and 'ISR' not in (line.tipo_retencion or '').upper()
                and 'ISV' not in (line.tipo_retencion or '').upper(),
            )
        return lines

    def _rows_from_book_lines(self, lines):
        estado_labels = dict(BOOK_ESTADO)
        rows = []
        for line in lines:
            move = line.move_id
            rows.append({
                'name': line.numero_factura or 'N/A',
                'date': line.fecha,
                'partner_name': line.proveedor or 'N/A',
                'partner_vat': line.rtn_proveedor or 'N/A',
                'base': line.base_imponible or 0,
                'type': line.tipo_retencion or 'N/A',
                'rate': line.porcentaje_retencion or 0,
                'amount': line.monto_retenido or 0,
                'total': move.amount_total if move else 0,
                'cai': move.cai_proveedor if move else 'N/A',
                'state_label': estado_labels.get(line.estado, line.estado or ''),
            })
        return rows

    def _rows_from_live_invoices(self, invoices):
        state_labels = dict(self.env['account.move']._fields['state'].selection)
        rows = []
        for invoice in invoices:
            info = self._get_retention_info(invoice)
            rows.append({
                'name': invoice.name or 'N/A',
                'date': invoice.date,
                'partner_name': invoice.commercial_partner_id.name or 'N/A',
                'partner_vat': invoice.commercial_partner_id.vat or 'N/A',
                'base': info['base'],
                'type': info['type'],
                'rate': info['rate'],
                'amount': info['amount'],
                'total': invoice.amount_total or 0,
                'cai': invoice.cai_proveedor or 'N/A',
                'state_label': state_labels.get(invoice.state, invoice.state),
            })
        return rows

    def _get_retention_rows(self):
        self.ensure_one()
        if self.data_source == 'book':
            self._validate_fiscal_report_source()
            lines = self._filter_retention_type_book(
                self._fiscal_report_selected_book(),
            )
            if not lines:
                raise ValidationError(_(
                    'No hay líneas de retenciones en el libro para el '
                    'período y filtros seleccionados.',
                ))
            return self._rows_from_book_lines(lines)

        invoices = self.get_retentions()
        if not invoices:
            raise ValidationError(_(
                'No se encontraron retenciones en vivo para el período y '
                'estado de documentos seleccionados.',
            ))
        return self._rows_from_live_invoices(invoices)

    def action_generate_report(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise ValidationError(_('La fecha desde no puede ser mayor a la fecha hasta'))
        rows = self._get_retention_rows()
        self.total_retentions = len(rows)
        self.total_amount = sum(r['amount'] for r in rows)
        self.total_base = sum(r['base'] for r in rows)
        return self.print_report(rows)

    def print_report(self, rows=None):
        if rows is None:
            rows = self._get_retention_rows()
        source_label = self._fiscal_source_label_for_excel()
        filename = f'Reporte_Retenciones_SAR_{self.date_from}_{self.date_to}.xlsx'
        stream = io.BytesIO()
        workbook = xlsxwriter.Workbook(stream, {'in_memory': True})
        encabezado = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        titulos = workbook.add_format({'bold': True, 'align': 'center'})
        subtitulos = workbook.add_format({'bold': True, 'align': 'center', 'text_wrap': True})
        detalle = workbook.add_format({})
        detalle_moneda = workbook.add_format({'num_format': 'L#,##0.00'})

        sheet = workbook.add_worksheet('Resumen General')
        sheet.merge_range(0, 0, 0, 5, 'REPORTE DE RETENCIONES SAR - HONDURAS', encabezado)
        sheet.merge_range(1, 0, 1, 5, f'Período: {self.date_from} - {self.date_to}', subtitulos)
        sheet.merge_range(2, 0, 2, 5, source_label, subtitulos)

        sheet.write(4, 0, 'Empresa:', titulos)
        sheet.write(4, 1, self.company_id.name, detalle)
        sheet.write(5, 0, 'RTN:', titulos)
        sheet.write(5, 1, self.company_id.vat or 'N/A', detalle)

        sheet.write(7, 0, 'TOTALES GENERALES', encabezado)
        sheet.write(8, 0, 'Concepto', titulos)
        sheet.write(9, 0, 'Total Retenciones', detalle)
        sheet.write(9, 1, len(rows), detalle)
        sheet.write(10, 0, 'Base Imponible Total', detalle)
        sheet.write(10, 2, sum(r['base'] for r in rows), detalle_moneda)

        sheet_detail = workbook.add_worksheet('Detalle por Retención')
        headers = [
            'Número Factura', 'Fecha', 'Proveedor', 'RTN Proveedor', 'Base Imponible',
            'Tipo Retención', 'Porcentaje', 'Monto Retenido', 'Total Factura',
            'CAI Proveedor', 'Estado',
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
            sheet_detail.write(row_idx, 4, row['base'], detalle_moneda)
            sheet_detail.write(row_idx, 5, row['type'], detalle)
            sheet_detail.write(row_idx, 6, f"{row['rate']}%", detalle)
            sheet_detail.write(row_idx, 7, row['amount'], detalle_moneda)
            sheet_detail.write(row_idx, 8, row['total'], detalle_moneda)
            sheet_detail.write(row_idx, 9, row['cai'], detalle)
            sheet_detail.write(row_idx, 10, row['state_label'], detalle)
            row_idx += 1

        sheet_summary = workbook.add_worksheet('Resumen por Tipo')
        summary_headers = [
            'Tipo de Retención', 'Cantidad', 'Base Imponible',
            'Monto Retenido', 'Promedio %',
        ]
        for col, header in enumerate(summary_headers):
            sheet_summary.write(0, col, header, titulos)

        retention_summary = {}
        for row in rows:
            retention_type = row['type']
            bucket = retention_summary.setdefault(
                retention_type,
                {'count': 0, 'base': 0, 'amount': 0, 'rates': []},
            )
            bucket['count'] += 1
            bucket['base'] += row['base']
            bucket['amount'] += row['amount']
            bucket['rates'].append(row['rate'])

        row_idx = 1
        for retention_type, data in retention_summary.items():
            avg_rate = sum(data['rates']) / len(data['rates']) if data['rates'] else 0
            sheet_summary.write(row_idx, 0, retention_type, detalle)
            sheet_summary.write(row_idx, 1, data['count'], detalle)
            sheet_summary.write(row_idx, 2, data['base'], detalle_moneda)
            sheet_summary.write(row_idx, 3, data['amount'], detalle_moneda)
            sheet_summary.write(row_idx, 4, f"{avg_rate:.2f}%", detalle)
            row_idx += 1

        workbook.close()
        export_id = self.env['kc_fiscal_hn.retentions_sar.excel'].create({
            'excel_file': base64.b64encode(stream.getvalue()),
            'file_name': filename,
        })
        stream.close()
        return {
            'view_mode': 'form',
            'res_id': export_id.id,
            'res_model': 'kc_fiscal_hn.retentions_sar.excel',
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def get_retentions(self):
        domain = [
            ('move_type', '=', 'in_invoice'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]
        domain.extend(self._live_move_state_domain())
        if self.retention_type == 'isr':
            domain.append(('invoice_line_ids.tax_ids.name', 'ilike', 'ISR'))
        elif self.retention_type == 'isv':
            domain.append(('invoice_line_ids.tax_ids.name', 'ilike', 'ISV'))
        return self.env['account.move'].search(domain)
    
    def _get_retention_info(self, invoice):
        """Obtener información de retenciones de una factura"""
        retention_info = {
            'base': 0,
            'type': 'N/A',
            'rate': 0,
            'amount': 0
        }
        
        for line in invoice.invoice_line_ids:
            if line.tax_ids:
                retention_info['base'] += line.price_subtotal
                
                for tax in line.tax_ids:
                    if 'ISR' in tax.name.upper():
                        retention_info['type'] = 'ISR'
                        retention_info['rate'] = tax.amount
                        retention_info['amount'] += tax.amount
                    elif 'ISV' in tax.name.upper():
                        retention_info['type'] = 'ISV'
                        retention_info['rate'] = tax.amount
                        retention_info['amount'] += tax.amount
                    else:
                        retention_info['type'] = 'Otra'
                        retention_info['rate'] = tax.amount
                        retention_info['amount'] += tax.amount
        
        return retention_info
    
    def action_download_excel(self):
        """Descargar archivo Excel"""
        if not self.excel_file:
            raise ValidationError(_('Primero debe generar el reporte'))
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=excel_file&filename_field=excel_filename&download=true',
            'target': 'self',
        }


class ReportRetentionsSarExcel(models.TransientModel):
    _name = 'kc_fiscal_hn.retentions_sar.excel'
    _description = 'Reporte de Retenciones SAR Excel'

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