# -*- coding: utf-8 -*-

import base64
import logging
from io import BytesIO

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .fiscal_period import (
    action_notify_and_reload,
    check_fiscal_period,
    month_bounds,
    numero_factura_ventas,
)

_logger = logging.getLogger(__name__)


def _export_book_excel(recordset, sheet_name, headers, rows):
    """Helper compartido para exportar libros SAR a Excel."""
    if not recordset:
        raise UserError(_('No hay líneas para exportar.'))
    filename = f'{sheet_name}_{fields.Date.context_today(recordset)}.xlsx'
    stream = BytesIO()
    workbook = xlsxwriter.Workbook(stream, {'in_memory': True})
    sheet = workbook.add_worksheet(sheet_name[:31])
    header_fmt = workbook.add_format({
        'bold': True, 'bg_color': '#D9E1F2', 'border': 1,
    })
    money_fmt = workbook.add_format({'num_format': 'L#,##0.00', 'border': 1})
    cell_fmt = workbook.add_format({'border': 1})
    for col, title in enumerate(headers):
        sheet.write(0, col, title, header_fmt)
    for row_idx, row in enumerate(rows, start=1):
        for col_idx, cell in enumerate(row):
            if isinstance(cell, (int, float)) and col_idx >= 4:
                sheet.write(row_idx, col_idx, cell, money_fmt)
            else:
                sheet.write(row_idx, col_idx, cell, cell_fmt)
    sheet.freeze_panes(1, 0)
    if rows:
        sheet.autofilter(0, 0, len(rows), len(headers) - 1)
    workbook.close()
    book = recordset[:1]
    att = recordset.env['ir.attachment'].create({
        'name': filename,
        'type': 'binary',
        'datas': base64.b64encode(stream.getvalue()),
        'mimetype': (
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ),
        'res_model': book._name,
        'res_id': book.id,
    })
    stream.close()
    return {
        'type': 'ir.actions.act_url',
        'url': f'/web/content/{att.id}?download=true',
        'target': 'self',
    }


class BookSales(models.Model):
    _name = 'kc_fiscal_hn.book.sales'
    _description = 'Libro de Ventas SAR Honduras'
    _order = 'date_from desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True,
    )
    date_from = fields.Date(string='Fecha Desde', required=True, tracking=True)
    date_to = fields.Date(string='Fecha Hasta', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        default=lambda self: self.env.company,
        required=True,
    )
    tipo_contribuyente = fields.Selection(
        related='company_id.tipo_contribuyente',
        readonly=True,
        store=True,
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('pending', 'Pendiente'),
        ('declared', 'Declarado'),
        ('rectified', 'Rectificado'),
    ], string='Estado', default='draft', tracking=True)
    fecha_declaracion = fields.Date(
        string='Fecha Declaración',
        readonly=True,
        tracking=True,
    )
    declarado_por = fields.Many2one(
        'res.users',
        string='Declarado por',
        readonly=True,
        tracking=True,
    )
    notas_rectificacion = fields.Text(string='Notas de Rectificación', tracking=True)
    line_ids = fields.One2many(
        'kc_fiscal_hn.book.sales.line',
        'book_id',
        string='Líneas',
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )

    total_ventas = fields.Monetary(
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_exento = fields.Monetary(
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_exonerado = fields.Monetary(
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_gravado_15 = fields.Monetary(
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_isv_15 = fields.Monetary(
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_gravado_18 = fields.Monetary(
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_isv_18 = fields.Monetary(
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_descuento = fields.Monetary(
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_general = fields.Monetary(
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_isv_ventas = fields.Monetary(
        string='Total ISV Ventas (Débito Fiscal)',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    debito_declarado_isv = fields.Monetary(
        string='Débito Fiscal Declarado en ISV',
        currency_field='currency_id',
        help='Ingrese el total del débito fiscal '
             'de su Declaración ISV para verificar '
             'consistencia con el Libro de Ventas.',
    )
    diferencia_debito_isv = fields.Monetary(
        string='Diferencia Débito ISV vs Ventas',
        compute='_compute_diferencia_debito',
        store=True,
        currency_field='currency_id',
    )
    consistencia_debito = fields.Selection([
        ('ok', 'Consistente'),
        ('diferencia', 'Hay diferencia'),
        ('sin_verificar', 'Sin verificar'),
    ], string='Consistencia Débito ISV',
       compute='_compute_diferencia_debito',
       store=True,
    )
    total_nc = fields.Monetary(
        string='Total Notas de Crédito',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_nd = fields.Monetary(
        string='Total Notas de Débito',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )

    @api.depends('date_from', 'date_to')
    def _compute_name(self):
        for book in self:
            if book.date_from and book.date_to:
                book.name = (
                    f'Libro Ventas SAR '
                    f'{book.date_from.strftime("%B %Y")}'
                )
            else:
                book.name = 'Libro Ventas SAR'

    @api.constrains('date_from', 'date_to', 'company_id')
    def _check_unique_period(self):
        for book in self:
            check_fiscal_period(book.date_from, book.date_to)
            duplicado = self.search([
                ('date_from', '=', book.date_from),
                ('date_to', '=', book.date_to),
                ('company_id', '=', book.company_id.id),
                ('id', '!=', book.id),
            ], limit=1)
            if duplicado:
                raise ValidationError(_(
                    'Ya existe un libro SAR para el período '
                    '%(desde)s - %(hasta)s en la empresa '
                    '%(empresa)s.\n'
                    'Libro existente: %(nombre)s '
                    '(Estado: %(estado)s)',
                    desde=book.date_from,
                    hasta=book.date_to,
                    empresa=book.company_id.name,
                    nombre=duplicado.name,
                    estado=duplicado.state,
                ))

    @api.onchange('date_from')
    def _onchange_date_from_period(self):
        if self.date_from:
            self.date_from, self.date_to = month_bounds(self.date_from)

    @api.onchange('date_to')
    def _onchange_date_to_period(self):
        if self.date_from and self.date_to:
            if (
                self.date_from.year != self.date_to.year
                or self.date_from.month != self.date_to.month
            ):
                _, self.date_to = month_bounds(self.date_from)

    @api.depends(
        'line_ids.amount_total',
        'line_ids.exento',
        'line_ids.exonerado',
        'line_ids.gravado_15',
        'line_ids.isv_15',
        'line_ids.gravado_18',
        'line_ids.isv_18',
        'line_ids.descuento',
        'line_ids.tipo_documento',
    )
    def _compute_totals(self):
        for book in self:
            facturas = book.line_ids.filtered(
                lambda l: l.tipo_documento == 'factura',
            )
            nc = book.line_ids.filtered(
                lambda l: l.tipo_documento == 'nota_credito',
            )
            nd = book.line_ids.filtered(
                lambda l: l.tipo_documento == 'nota_debito',
            )
            book.total_exento = sum(book.line_ids.mapped('exento'))
            book.total_exonerado = sum(book.line_ids.mapped('exonerado'))
            book.total_gravado_15 = sum(book.line_ids.mapped('gravado_15'))
            book.total_isv_15 = sum(book.line_ids.mapped('isv_15'))
            book.total_gravado_18 = sum(book.line_ids.mapped('gravado_18'))
            book.total_isv_18 = sum(book.line_ids.mapped('isv_18'))
            book.total_descuento = sum(book.line_ids.mapped('descuento'))
            book.total_nc = sum(nc.mapped('amount_total'))
            book.total_nd = sum(nd.mapped('amount_total'))
            book.total_ventas = sum(facturas.mapped('amount_total'))
            book.total_general = (
                book.total_ventas + book.total_nd - book.total_nc
            )
            book.total_isv_ventas = (
                sum(book.line_ids.mapped('isv_15'))
                + sum(book.line_ids.mapped('isv_18'))
            )

    @api.depends(
        'total_isv_ventas',
        'debito_declarado_isv',
    )
    def _compute_diferencia_debito(self):
        for book in self:
            if not book.debito_declarado_isv:
                book.diferencia_debito_isv = 0
                book.consistencia_debito = 'sin_verificar'
                continue
            diff = abs(
                book.total_isv_ventas - book.debito_declarado_isv,
            )
            book.diferencia_debito_isv = diff
            book.consistencia_debito = (
                'ok' if diff <= 1.0 else 'diferencia'
            )

    @staticmethod
    def _numero_factura_libro(move):
        return numero_factura_ventas(move)

    @staticmethod
    def _prepare_line_vals_from_move(book, move):
        """Construye valores de línea desde account.move."""
        zero = 0.0
        tipo = BookSales._tipo_documento_from_move(move)
        numero = BookSales._numero_factura_libro(move)
        if not numero:
            return None

        if move.state == 'cancel':
            return {
                'book_id': book.id,
                'fecha': move.invoice_date or move.date,
                'numero_factura': numero,
                'rtn_cliente': move.commercial_partner_id.vat or '',
                'cliente': _('Factura anulada'),
                'exento': zero,
                'exonerado': zero,
                'gravado_15': zero,
                'isv_15': zero,
                'gravado_18': zero,
                'isv_18': zero,
                'descuento': zero,
                'amount_total': zero,
                'cai': move.cai or '',
                'tipo_documento': tipo,
                'invoice_id': move.id,
                'no_orden_compra_exenta': '',
                'no_constancia_exonerado': '',
                'es_anulada': True,
            }

        if move.state != 'posted':
            return None

        return {
            'book_id': book.id,
            'fecha': move.invoice_date,
            'numero_factura': numero,
            'rtn_cliente': move.commercial_partner_id.vat or '',
            'cliente': move.commercial_partner_id.name,
            'exento': move.amount_exento,
            'exonerado': move.amount_exonerado,
            'gravado_15': move.gravado_isv15,
            'isv_15': move.amount_isv15,
            'gravado_18': move.gravado_isv18,
            'isv_18': move.amount_isv18,
            'descuento': move.amount_discount,
            'amount_total': move.amount_total,
            'cai': move.cai or '',
            'tipo_documento': tipo,
            'invoice_id': move.id,
            'no_orden_compra_exenta': move.noOrdenCompraExenta or '',
            'no_constancia_exonerado': move.noConsRegistroExonerado or '',
            'es_anulada': False,
        }

    @staticmethod
    def _tipo_documento_from_move(move):
        if move.move_type == 'out_refund':
            return 'nota_credito'
        if move.journal_id.document_fiscal == 'debit':
            return 'nota_debito'
        return 'factura'

    @api.model
    def action_generar_desde_facturas(
        self, date_from, date_to, company_id=None, replace=False,
    ):
        """Compatibilidad con wizard de generación legacy."""
        company = (
            self.env['res.company'].browse(company_id)
            if company_id else self.env.company
        )
        book = self.search([
            ('date_from', '=', date_from),
            ('date_to', '=', date_to),
            ('company_id', '=', company.id),
        ], limit=1)
        if not book:
            book = self.create({
                'date_from': date_from,
                'date_to': date_to,
                'company_id': company.id,
            })
        elif replace:
            book._clear_book()
        return book.action_generate()

    def action_generate(self):
        self.ensure_one()
        if self.state == 'declared':
            raise UserError(_(
                'No puede regenerar un libro ya declarado al SAR.',
            ))
        if not self.date_from or not self.date_to:
            raise UserError(_('Configure las fechas del período.'))
        check_fiscal_period(self.date_from, self.date_to)

        self._clear_book()

        domain = [
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', 'in', ['posted', 'cancel']),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('journal_id.type', '=', 'sale'),
        ]
        moves = self.env['account.move'].search(
            domain, order='invoice_date asc, name asc',
        )

        Line = self.env['kc_fiscal_hn.book.sales.line']
        lines_vals = []
        for move in moves:
            vals = self._prepare_line_vals_from_move(self, move)
            if vals:
                lines_vals.append(vals)

        Line.with_context(skip_book_line_lock=True).sudo().create(lines_vals)

        moves_in_book = moves.filtered(
            lambda m: self._numero_factura_libro(m),
        )
        for move in moves_in_book:
            move.write({
                'in_libro_ventas': True,
                'libro_ventas_id': self.id,
            })

        self.state = 'pending'

        n_fact = len([v for v in lines_vals if v['tipo_documento'] == 'factura'])
        n_nc = len([v for v in lines_vals if v['tipo_documento'] == 'nota_credito'])
        n_nd = len([v for v in lines_vals if v['tipo_documento'] == 'nota_debito'])

        if not lines_vals and moves:
            raise UserError(_(
                'No se pudieron generar líneas del libro de ventas.\n\n'
                'Hay %(n)s documento(s) en el período, pero ninguno tiene '
                'numeración fiscal válida.\n\n'
                'Confirme las facturas de venta (no deben quedar con '
                'número «/») y verifique que el diario de ventas tenga '
                'Documento Fiscal = «Factura Cliente».',
                n=len(moves),
            ))

        return action_notify_and_reload(
            self,
            _('Libro Generado'),
            _(
                'Se generaron %d líneas (%d facturas, %d NC, %d ND).',
                len(lines_vals), n_fact, n_nc, n_nd,
            ),
        )

    def action_declare(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_(
                'El libro no tiene líneas. Genere el libro primero.',
            ))
        if self.consistencia_debito == 'diferencia':
            raise UserError(_(
                'No puede declarar el libro.\n\n'
                'Hay una diferencia de L %(diff).2f '
                'entre el ISV de ventas del libro '
                '(L %(libro).2f) y el débito fiscal '
                'declarado en ISV (L %(isv).2f).\n\n'
                'El SAR cruza estos valores. '
                'Corrija antes de declarar.',
                diff=self.diferencia_debito_isv,
                libro=self.total_isv_ventas,
                isv=self.debito_declarado_isv,
            ))
        self.write({
            'state': 'declared',
            'fecha_declaracion': fields.Date.context_today(self),
            'declarado_por': self.env.user.id,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Libro Declarado'),
                'message': _(
                    'El libro fue marcado como declarado al SAR por %s.',
                    self.env.user.name,
                ),
                'type': 'success',
            },
        }

    def action_rectify(self):
        self.ensure_one()
        if not self.notas_rectificacion:
            raise UserError(_(
                'Debe ingresar las notas de rectificación antes de rectificar.',
            ))
        self.write({'state': 'rectified'})

    def _clear_book(self):
        for line in self.line_ids:
            if line.invoice_id:
                line.invoice_id.write({
                    'in_libro_ventas': False,
                    'libro_ventas_id': False,
                })
        self.line_ids.with_context(skip_book_line_lock=True).sudo().unlink()

    def action_export_excel(self):
        self.ensure_one()
        return self.action_exportar_excel()

    def action_exportar_excel(self):
        if not self.line_ids:
            raise UserError(_('No hay líneas para exportar.'))
        headers = [
            'Fecha', 'N° Factura', 'Tipo', 'RTN Cliente', 'Cliente',
            'Exento', 'Exonerado', 'Gravado 15%', 'ISV 15%',
            'Gravado 18%', 'ISV 18%', 'Descuento', 'Total', 'CAI',
        ]
        tipo_labels = dict(self.line_ids._fields['tipo_documento'].selection)
        rows = []
        for line in self.line_ids:
            rows.append([
                str(line.fecha or ''),
                line.numero_factura or '',
                tipo_labels.get(line.tipo_documento, ''),
                line.rtn_cliente or '',
                line.cliente or '',
                line.exento,
                line.exonerado,
                line.gravado_15,
                line.isv_15,
                line.gravado_18,
                line.isv_18,
                line.descuento,
                line.amount_total,
                line.cai or '',
            ])
        from .book_sales import _export_book_excel
        return _export_book_excel(self, 'Libro_Ventas_SAR', headers, rows)


class BookSalesLine(models.Model):
    _name = 'kc_fiscal_hn.book.sales.line'
    _description = 'Línea Libro de Ventas SAR'
    _order = 'fecha asc, numero_factura asc'
    _inherit = ['kc.fiscal.book.line.mixin']

    book_id = fields.Many2one(
        'kc_fiscal_hn.book.sales',
        string='Libro',
        required=True,
        ondelete='cascade',
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Factura',
        readonly=True,
        ondelete='set null',
    )
    tipo_documento = fields.Selection([
        ('factura', 'Factura'),
        ('nota_credito', 'Nota de Crédito'),
        ('nota_debito', 'Nota de Débito'),
    ], string='Tipo', default='factura', readonly=True)
    es_anulada = fields.Boolean(
        string='Anulada',
        default=False,
        readonly=True,
    )

    fecha = fields.Date(string='Fecha', required=True, readonly=True)
    numero_factura = fields.Char(string='N° Factura', required=True, readonly=True)
    rtn_cliente = fields.Char(string='RTN Cliente', readonly=True)
    cliente = fields.Char(string='Cliente', required=True, readonly=True)
    exento = fields.Monetary(string='Exento', currency_field='currency_id', readonly=True)
    exonerado = fields.Monetary(string='Exonerado', currency_field='currency_id', readonly=True)
    gravado_15 = fields.Monetary(string='Gravado 15%', currency_field='currency_id', readonly=True)
    isv_15 = fields.Monetary(string='ISV 15%', currency_field='currency_id', readonly=True)
    gravado_18 = fields.Monetary(string='Gravado 18%', currency_field='currency_id', readonly=True)
    isv_18 = fields.Monetary(string='ISV 18%', currency_field='currency_id', readonly=True)
    descuento = fields.Monetary(string='Descuento', currency_field='currency_id', readonly=True)
    amount_total = fields.Monetary(string='Total', currency_field='currency_id', readonly=True)
    cai = fields.Char(string='CAI', readonly=True)
    no_orden_compra_exenta = fields.Char(string='N° OC Exenta', readonly=True)
    no_constancia_exonerado = fields.Char(string='N° Constancia Exonerado', readonly=True)
    state = fields.Selection(
        related='book_id.state',
        string='Estado',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='book_id.currency_id',
    )

    def _is_editable(self):
        return False
