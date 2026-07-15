# -*- coding: utf-8 -*-

import datetime
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .excel_export import build_excel_attachment

_logger = logging.getLogger(__name__)


class ReportDmcList(models.TransientModel):
    _name = 'kc_fiscal_hn.wizard.dmc'
    _description = 'Reporte DMC'
    _inherit = ['kc.fiscal.report.source.mixin']

    company_id = fields.Many2one(
        'res.company', 'Company', required=True,
        default=lambda s: s.env.company.id, index=True,
    )
    fecha_desde = fields.Date(
        string="Fecha Desde", default=datetime.date.today(), required=True,
    )
    fecha_hasta = fields.Date(
        string="Fecha Hasta", default=datetime.date.today(), required=True,
    )
    book_purchases_id = fields.Many2one(
        'kc_fiscal_hn.book.purchases',
        string='Libro / Declaración DMC',
    )
    available_book_purchases_ids = fields.Many2many(
        'kc_fiscal_hn.book.purchases',
        compute='_compute_available_book_purchases_ids',
    )
    book_period_label = fields.Char(
        string='Libro / Período',
        compute='_compute_fiscal_book_display',
    )

    @api.depends('company_id', 'fecha_desde', 'fecha_hasta')
    def _compute_available_book_purchases_ids(self):
        for wizard in self:
            wizard.available_book_purchases_ids = wizard._search_books_for_period()

    @api.onchange('book_purchases_id')
    def _onchange_book_purchases_id(self):
        self._compute_fiscal_book_display()

    def _fiscal_report_book_model(self):
        return 'kc_fiscal_hn.book.purchases'

    def _fiscal_report_book_kind(self):
        return 'header'

    def _fiscal_report_selected_book(self):
        return self.book_purchases_id

    def _row_from_move(self, move):
        clase_documento = ''
        cai_proveedor = ''
        f_documento = ''
        r_documento = ''
        costo = gasto = deducible = ''
        if move.class_document_sar == 'FA':
            cai_proveedor = move.cai_proveedor
            f_documento = move.correlativo_proveedor
            clase_documento = 'FA-FACTURA'
        elif move.class_document_sar == 'OC':
            r_documento = move.correlativo_proveedor
            clase_documento = 'OC-OTROS COMPROBANTES DE PAGO'

        if move.montos_sar == 'costo':
            costo = move.amount_isv15 + move.amount_isv18
        elif move.montos_sar == 'gasto':
            gasto = move.amount_isv15 + move.amount_isv18
        elif move.montos_sar == 'no_deducible':
            deducible = move.amount_isv15 + move.amount_isv18

        return {
            'rtn': move.commercial_partner_id.vat,
            'proveedor': move.commercial_partner_id.name,
            'clase': clase_documento,
            'cai': cai_proveedor,
            'f_documento': f_documento,
            'r_documento': r_documento,
            'fecha_emision': move.femision_proveedor or '',
            'fecha_contable': move.date.strftime('%d-%m-%Y') if move.date else '',
            'oce': move.noOrdenCompraExenta or '',
            'importe_exento': move.amount_exento,
            'importe_nosujeto': '',
            'resolucion': '',
            'importe_exonerado': move.amount_exonerado,
            'importe_isv15': move.gravado_isv15,
            'importe_isv18': move.gravado_isv18,
            'costo': costo,
            'gasto': gasto,
            'deducible': deducible,
        }

    def _row_from_book_line(self, line):
        move = line.invoice_id
        clase = line.clase_documento or ''
        f_documento = line.numero_factura or ''
        r_documento = ''
        if clase.startswith('OC') or 'OC' in clase:
            r_documento = line.numero_factura or ''
            f_documento = ''
        fecha_contable = ''
        if move and move.date:
            fecha_contable = move.date.strftime('%d-%m-%Y')
        elif line.fecha:
            fecha_contable = line.fecha.strftime('%d-%m-%Y')

        return {
            'rtn': line.rtn_proveedor,
            'proveedor': line.proveedor,
            'clase': clase,
            'cai': line.cai_proveedor or '',
            'f_documento': f_documento,
            'r_documento': r_documento,
            'fecha_emision': line.fecha_emision or '',
            'fecha_contable': fecha_contable,
            'oce': move.noOrdenCompraExenta if move else '',
            'importe_exento': line.exento,
            'importe_nosujeto': '',
            'resolucion': '',
            'importe_exonerado': line.exonerado,
            'importe_isv15': line.gravado_15,
            'importe_isv18': line.gravado_18,
            'costo': line.costo,
            'gasto': line.gasto,
            'deducible': line.no_deducible,
        }

    def get_invoice(self):
        if self.data_source == 'book':
            self._validate_fiscal_report_source()
            lines = self.book_purchases_id.line_ids.sorted(
                key=lambda line: (line.fecha or '', line.numero_factura or ''),
            )
            if not lines:
                raise ValidationError(_(
                    'El libro DMC seleccionado no tiene líneas para exportar.',
                ))
            return [self._row_from_book_line(line) for line in lines]

        domain = [
            ('company_id', '=', self.company_id.id),
            ('invoice_date', '>=', self.fecha_desde),
            ('invoice_date', '<=', self.fecha_hasta),
            ('move_type', '=', 'in_invoice'),
        ]
        domain.extend(self._live_move_state_domain())
        invoices = self.env['account.move'].search(domain)
        if not invoices:
            raise ValidationError(_(
                'No se encontraron compras en vivo para el período y '
                'estado de documentos seleccionados.',
            ))
        return [self._row_from_move(move) for move in invoices]

    def print_report(self):
        rows = self.get_invoice()
        source_label = self._fiscal_source_label_for_excel()
        filename = f'dmc_{self.fecha_desde}_{self.fecha_hasta}.xlsx'

        def _build(workbook, styles):
            sheet = workbook.add_worksheet('Detalle Compras')
            enc = styles['encabezado']
            sub = styles['subtitulos']
            det = styles['detalle']
            mon = styles['moneda']

            sheet.merge_range(0, 1, 0, 3, 'Hoja EXCEL N°1 Detalle Compras Locales', enc)
            sheet.merge_range(1, 4, 1, 8, 'Numero de Documento Fiscal', sub)
            sheet.merge_range(0, 9, 0, 21, source_label, sub)

            headers = [
                '200-R.T.N', 'Nombres Apellidos o Razón Social del Proveedor',
                '600-CLASE DE DOCUMENTO', '7-CAI', '8-N° Documento',
                'Establecimiento', 'Punto de Emision', 'Tipo de Documento', 'Correlativo',
                '71-N° Documento', '900-Fecha emisión', '100-Fecha contable', '140-Nº OCE',
                '110-Importe exento', '1110-Importe no sujeto', '130-Nº resolución',
                '120-Importe exonerado', '1511-Importe base 15%', '1611-Importe base 18%',
                '270-Monto al costo', '280-Monto al gasto', '290-Valor no deducible',
            ]
            for col, title in enumerate(headers):
                sheet.write(2, col, title, sub)

            row = 3
            for i in rows:
                estable = emision = tipo = correlativo = ''
                fiscal_documento = i['f_documento'] or ''
                if fiscal_documento and '-' in fiscal_documento:
                    partes = fiscal_documento.split('-')
                    if len(partes) == 4:
                        estable, emision, tipo, correlativo = partes

                sheet.write(row, 0, i['rtn'], det)
                sheet.write(row, 1, i['proveedor'], det)
                sheet.write(row, 2, i['clase'], det)
                sheet.write(row, 3, i['cai'], det)
                sheet.write(row, 4, fiscal_documento, det)
                sheet.write(row, 5, estable, det)
                sheet.write(row, 6, emision, det)
                sheet.write(row, 7, tipo, det)
                sheet.write(row, 8, correlativo, det)
                sheet.write(row, 9, i['r_documento'], det)
                sheet.write(row, 10, i['fecha_emision'], det)
                sheet.write(row, 11, i['fecha_contable'], det)
                sheet.write(row, 12, i['oce'], det)
                sheet.write(row, 13, i['importe_exento'], mon)
                sheet.write(row, 14, i['importe_nosujeto'], mon)
                sheet.write(row, 15, i['resolucion'], det)
                sheet.write(row, 16, i['importe_exonerado'], mon)
                sheet.write(row, 17, i['importe_isv15'], mon)
                sheet.write(row, 18, i['importe_isv18'], mon)
                sheet.write(row, 19, i['costo'], mon)
                sheet.write(row, 20, i['gasto'], mon)
                sheet.write(row, 21, i['deducible'], mon)
                row += 1

            sheet.freeze_panes(3, 0)
            sheet.autofilter(2, 0, max(row - 1, 2), len(headers) - 1)
            sheet.set_column(0, 21, 14)

        return build_excel_attachment(
            self.env,
            filename=filename,
            excel_model='kc_fiscal_hn.dmc.excel',
            build_callback=_build,
        )


class ReportInvoiceExcel(models.TransientModel):
    _name = "kc_fiscal_hn.dmc.excel"
    _description = "Reporte DMC Excel"

    excel_file = fields.Binary('Lista Factura', readonly=True)
    file_name = fields.Char('Excel File', size=64)
