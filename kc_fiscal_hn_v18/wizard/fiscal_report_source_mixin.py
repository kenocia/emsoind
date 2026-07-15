# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..models.fiscal_book_mixin import BOOK_ESTADO

BOOK_HEADER_STATE_LABELS = {
    'draft': _('Borrador'),
    'pending': _('Pendiente'),
    'declared': _('Declarado'),
    'rectified': _('Rectificado'),
}


class FiscalReportSourceMixin(models.AbstractModel):
    """Selector de fuente Libro SAR vs facturas en vivo para informes Excel."""

    _name = 'kc.fiscal.report.source.mixin'
    _description = 'Mixin fuente de datos informes fiscales'

    data_source = fields.Selection(
        [
            ('live', 'Facturas en vivo'),
            ('book', 'Libro SAR'),
        ],
        string='Fuente de datos',
        default='live',
        required=True,
    )
    has_book_available = fields.Boolean(
        string='Libro disponible',
        compute='_compute_fiscal_book_availability',
    )
    live_document_state = fields.Selection(
        [
            ('posted', 'Solo confirmadas'),
            ('posted_cancel', 'Confirmadas y anuladas'),
            ('draft', 'Borrador'),
            ('cancel', 'Anuladas'),
            ('all', 'Todos los estados'),
        ],
        string='Estado de documentos',
        default='posted',
        required=True,
    )
    book_state_display = fields.Char(
        string='Estado del libro / declaración',
        compute='_compute_fiscal_book_display',
    )
    book_declaration_date = fields.Date(
        string='Fecha declaración SAR',
        compute='_compute_fiscal_book_display',
    )
    book_declared_by = fields.Char(
        string='Declarado por',
        compute='_compute_fiscal_book_display',
    )

    # --- Hooks para cada wizard ---

    def _fiscal_report_book_model(self):
        """Nombre del modelo de libro. Override en subclase."""
        return False

    def _fiscal_report_book_kind(self):
        """'header' (cabecera + líneas) o 'flat' (líneas por período)."""
        return 'header'

    def _fiscal_report_date_from(self):
        return getattr(self, 'date_from', None) or getattr(self, 'fecha_desde', None)

    def _fiscal_report_date_to(self):
        return getattr(self, 'date_to', None) or getattr(self, 'fecha_hasta', None)

    def _fiscal_report_company(self):
        return self.company_id

    def _fiscal_report_selected_book(self):
        """Registro de libro (cabecera) o recordset de líneas (flat). Override."""
        return self.env[self._fiscal_report_book_model()].browse()

    def _fiscal_report_book_has_lines(self, book):
        if self._fiscal_report_book_kind() == 'header':
            return bool(book.line_ids)
        return bool(book)

    def _search_books_for_period(self):
        """Libros con líneas que intersectan el período del wizard."""
        model_name = self._fiscal_report_book_model()
        if not model_name:
            return self.env[model_name].browse()

        date_from = self._fiscal_report_date_from()
        date_to = self._fiscal_report_date_to()
        company = self._fiscal_report_company()
        if not date_from or not date_to or not company:
            return self.env[model_name].browse()

        if self._fiscal_report_book_kind() == 'header':
            books = self.env[model_name].search([
                ('company_id', '=', company.id),
                ('date_from', '<=', date_to),
                ('date_to', '>=', date_from),
            ], order='date_from desc, id desc')
            return books.filtered(self._fiscal_report_book_has_lines)

        return self.env[model_name].search([
            ('company_id', '=', company.id),
            ('periodo_desde', '=', date_from),
            ('periodo_hasta', '=', date_to),
        ], order='fecha asc, id asc')

    @api.depends('company_id')
    def _compute_fiscal_book_availability(self):
        for wizard in self:
            wizard.has_book_available = bool(wizard._search_books_for_period())

    @api.depends('company_id', 'data_source')
    def _compute_fiscal_book_display(self):
        for wizard in self:
            wizard.book_state_display = False
            wizard.book_declaration_date = False
            wizard.book_declared_by = False
            if hasattr(wizard, 'book_period_label'):
                wizard.book_period_label = False
            if wizard.data_source != 'book' or not wizard.has_book_available:
                continue
            wizard._fill_book_display_fields()

    def _fill_book_display_fields(self):
        self.ensure_one()
        kind = self._fiscal_report_book_kind()
        if kind == 'header':
            book = self._fiscal_report_selected_book()
            if not book:
                return
            self.book_state_display = BOOK_HEADER_STATE_LABELS.get(
                book.state, book.state or '',
            )
            self.book_declaration_date = book.fecha_declaracion
            self.book_declared_by = (
                book.declarado_por.name if book.declarado_por else False
            )
            if hasattr(self, 'book_period_label'):
                self.book_period_label = book.display_name
            return

        lines = self._fiscal_report_selected_book()
        if not lines:
            return
        date_from = self._fiscal_report_date_from()
        date_to = self._fiscal_report_date_to()
        if hasattr(self, 'book_period_label'):
            self.book_period_label = _(
                'Período %(desde)s — %(hasta)s (%(n)s líneas)',
                desde=date_from,
                hasta=date_to,
                n=len(lines),
            )
        estados = set(lines.mapped('estado'))
        estado_labels = dict(BOOK_ESTADO)
        if len(estados) == 1:
            self.book_state_display = estado_labels.get(
                estados.pop(), _('Pendiente'),
            )
        elif 'declarado' in estados:
            self.book_state_display = _('Parcialmente declarado')
        else:
            self.book_state_display = _('Pendiente')

        declared_lines = lines.filtered(lambda l: l.fecha_declaracion)
        if declared_lines:
            self.book_declaration_date = declared_lines[0].fecha_declaracion
            self.book_declared_by = (
                declared_lines[0].declarado_por.name
                if declared_lines[0].declarado_por else False
            )

    @api.onchange(
        'date_from', 'date_to', 'fecha_desde', 'fecha_hasta', 'company_id',
    )
    def _onchange_fiscal_report_period(self):
        self._compute_fiscal_book_availability()
        books = self._search_books_for_period()
        if not books:
            self.data_source = 'live'
            self._clear_book_selection()
            return

        if self._fiscal_report_book_kind() == 'header':
            selected = self._fiscal_report_selected_book()
            if selected and selected not in books:
                self._clear_book_selection()
            if not self._fiscal_report_selected_book() and len(books) == 1:
                self._assign_single_book(books[0])
        self._compute_fiscal_book_display()

    @api.onchange('data_source')
    def _onchange_data_source(self):
        if self.data_source == 'book' and not self.has_book_available:
            self.data_source = 'live'
        elif self.data_source == 'live':
            self._clear_book_selection()
        self._compute_fiscal_book_display()

    def _clear_book_selection(self):
        if hasattr(self, 'book_sales_id'):
            self.book_sales_id = False
        if hasattr(self, 'book_purchases_id'):
            self.book_purchases_id = False

    def _assign_single_book(self, book):
        if hasattr(self, 'book_sales_id'):
            self.book_sales_id = book
        elif hasattr(self, 'book_purchases_id'):
            self.book_purchases_id = book

    def _live_move_state_domain(self):
        mapping = {
            'posted': [('state', '=', 'posted')],
            'posted_cancel': [('state', 'in', ['posted', 'cancel'])],
            'draft': [('state', '=', 'draft')],
            'cancel': [('state', '=', 'cancel')],
            'all': [],
        }
        return list(mapping.get(self.live_document_state, mapping['posted']))

    def _validate_fiscal_report_source(self):
        self.ensure_one()
        if self.data_source == 'book':
            if not self.has_book_available:
                raise ValidationError(_(
                    'No existe un libro SAR con líneas para el período '
                    'seleccionado. Genere el libro primero o use '
                    '«Facturas en vivo».',
                ))
            if self._fiscal_report_book_kind() == 'header':
                book = self._fiscal_report_selected_book()
                if not book:
                    raise ValidationError(_(
                        'Seleccione el libro SAR o declaración del período.',
                    ))
                if not book.line_ids:
                    raise ValidationError(_(
                        'El libro seleccionado no tiene líneas. '
                        'Genere el libro antes de exportar.',
                    ))
            elif not self._search_books_for_period():
                raise ValidationError(_(
                    'No hay líneas de libro SAR para el período seleccionado.',
                ))

    def _fiscal_source_label_for_excel(self):
        self.ensure_one()
        if self.data_source == 'live':
            state_label = dict(
                self._fields['live_document_state'].selection,
            ).get(self.live_document_state, '')
            return _('Facturas en vivo — %(state)s', state=state_label)
        parts = [_('Libro SAR')]
        if self.book_state_display:
            parts.append(self.book_state_display)
        if self.book_declaration_date:
            parts.append(str(self.book_declaration_date))
        if self.book_declared_by:
            parts.append(self.book_declared_by)
        book = self._fiscal_report_selected_book()
        if book and self._fiscal_report_book_kind() == 'header':
            parts.insert(1, book.display_name)
        return ' — '.join(filter(None, parts))
