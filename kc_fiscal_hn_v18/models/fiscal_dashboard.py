# -*- coding: utf-8 -*-
import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class FiscalDashboard(models.TransientModel):
    _name = 'kc_fiscal_hn.dashboard'
    _description = 'Dashboard Fiscal SAR Honduras'
    _copy = False

    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        default=fields.Date.today,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
    )
    all_sequences = fields.Boolean(
        string='Todas las secuencias',
        default=True,
        help='Si está activo, incluye todas las secuencias fiscales de la empresa.',
    )
    fiscal_sequence_ids = fields.Many2many(
        'ir.sequence',
        'kc_fiscal_dashboard_sequence_rel',
        'dashboard_id',
        'sequence_id',
        string='Secuencias Fiscales',
        domain="[('is_fiscal', '=', True), ('company_id', '=', company_id)]",
        help='Filtra por puntos de impresión / secuencias de venta o compra.',
    )
    secuencias_seleccionadas = fields.Integer(
        string='Secuencias seleccionadas',
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )

    @api.depends('date_from', 'date_to', 'company_id')
    def _compute_display_name(self) -> None:
        for rec in self:
            rec.display_name = _('Dashboard Fiscal SAR')

    @api.model
    def _get_user_dashboard(self):
        """Un solo dashboard reutilizable por usuario y empresa."""
        domain = [
            ('create_uid', '=', self.env.user.id),
            ('company_id', '=', self.env.company.id),
        ]
        dashboards = self.search(domain, order='id desc')
        dashboard = dashboards[:1]
        if dashboards - dashboard:
            (dashboards - dashboard).sudo().unlink()
        if not dashboard:
            dashboard = self.create({})
        return dashboard

    tipo_contribuyente = fields.Selection(
        related='company_id.tipo_contribuyente',
        readonly=True,
    )
    obligado_dmc = fields.Boolean(
        related='company_id.obligado_dmc',
        readonly=True,
    )
    es_agente_retencion = fields.Boolean(
        related='company_id.es_agente_retencion',
        readonly=True,
    )
    fecha_vencimiento_dmc_mes = fields.Date(
        string='Vencimiento DMC este mes',
        compute='_compute_vencimiento_dmc_actual',
    )
    dias_vencimiento_dmc = fields.Integer(
        string='Días para vencer DMC',
        compute='_compute_vencimiento_dmc_actual',
    )
    libro_mes_generado = fields.Boolean(
        string='Libro del mes generado',
        compute='_compute_estado_libro_mes',
    )
    libro_mes_declarado = fields.Boolean(
        string='Libro del mes declarado',
        compute='_compute_estado_libro_mes',
    )
    estado_consistencia_periodo = fields.Selection([
        ('ok', 'Todo consistente'),
        ('pendiente', 'Libros no declarados'),
        ('diferencia', 'Diferencias detectadas'),
        ('sin_libros', 'Sin libros generados'),
    ], string='Estado Consistencia SAR',
       compute='_compute_estado_consistencia',
    )

    data_source = fields.Selection([
        ('live', 'Tiempo Real (Facturas)'),
        ('book', 'Libro SAR Declarado'),
        ('mixed', 'Mixto'),
    ], string='Fuente de Datos', default='live', readonly=True)
    periodo_declarado = fields.Boolean(
        string='Período Declarado al SAR',
        readonly=True,
        default=False,
    )
    fecha_declaracion = fields.Date(
        string='Fecha de Declaración',
        readonly=True,
    )
    declarado_por = fields.Char(
        string='Declarado por',
        readonly=True,
    )

    total_ventas = fields.Monetary(
        string='Total Ventas',
        currency_field='currency_id',
        readonly=True,
    )
    total_facturas_ventas = fields.Integer(
        string='N° Facturas Emitidas',
        readonly=True,
    )
    isv_ventas = fields.Monetary(
        string='ISV Ventas',
        currency_field='currency_id',
        readonly=True,
    )
    isv_ventas_15 = fields.Monetary(
        string='ISV 15%',
        currency_field='currency_id',
        readonly=True,
    )
    isv_ventas_18 = fields.Monetary(
        string='ISV 18%',
        currency_field='currency_id',
        readonly=True,
    )
    ventas_exentas = fields.Monetary(
        string='Ventas Exentas',
        currency_field='currency_id',
        readonly=True,
    )
    ventas_exoneradas = fields.Monetary(
        string='Ventas Exoneradas',
        currency_field='currency_id',
        readonly=True,
    )
    ticket_promedio = fields.Monetary(
        string='Ticket Promedio',
        currency_field='currency_id',
        readonly=True,
    )
    clientes_unicos = fields.Integer(
        string='Clientes Únicos',
        readonly=True,
    )
    facturas_sin_rtn = fields.Integer(
        string='Facturas sin RTN',
        readonly=True,
    )

    total_compras = fields.Monetary(
        string='Total Compras',
        currency_field='currency_id',
        readonly=True,
    )
    total_facturas_compras = fields.Integer(
        string='N° Facturas Compra',
        readonly=True,
    )
    isv_compras = fields.Monetary(
        string='ISV Compras',
        currency_field='currency_id',
        readonly=True,
    )

    isv_neto_pagar = fields.Monetary(
        string='ISV Neto a Pagar',
        currency_field='currency_id',
        readonly=True,
    )
    retenciones_aplicadas = fields.Monetary(
        string='Retenciones Aplicadas',
        currency_field='currency_id',
        readonly=True,
    )
    comprobantes_retencion = fields.Integer(
        string='Comprobantes Retención',
        readonly=True,
    )

    notas_credito = fields.Integer(string='Notas de Crédito', readonly=True)
    monto_notas_credito = fields.Monetary(
        string='Monto NC',
        currency_field='currency_id',
        readonly=True,
    )
    notas_debito = fields.Integer(string='Notas de Débito', readonly=True)
    facturas_anuladas = fields.Integer(string='Facturas Anuladas', readonly=True)
    guias_remision = fields.Integer(string='Guías de Remisión', readonly=True)

    correlativos_usados = fields.Integer(string='Correlativos Usados', readonly=True)
    correlativos_disponibles = fields.Integer(
        string='Correlativos Disponibles',
        readonly=True,
    )
    dias_vencimiento_cai = fields.Integer(string='Días CAI Vigente', readonly=True)
    porcentaje_uso_secuencia = fields.Float(
        string='% Uso Secuencia',
        digits=(5, 2),
        readonly=True,
    )

    timeline_chart_html = fields.Html(
        string='Línea de Tiempo',
        readonly=True,
        sanitize=False,
    )
    dona_isv_html = fields.Html(
        string='Distribución ISV',
        readonly=True,
        sanitize=False,
    )
    secuencias_status_html = fields.Html(
        string='Estado Secuencias',
        readonly=True,
        sanitize=False,
    )

    contactos_total = fields.Integer(string='Total Contactos', readonly=True)
    contactos_hn_total = fields.Integer(string='HN — Total', readonly=True)
    contactos_hn_con_empresa = fields.Integer(string='HN — Con RTN Empresa', readonly=True)
    contactos_hn_con_natural = fields.Integer(string='HN — Con RTN Natural', readonly=True)
    contactos_hn_sin_empresa = fields.Integer(string='HN — Sin RTN Empresa', readonly=True)
    contactos_hn_sin_natural = fields.Integer(string='HN — Sin RTN Natural', readonly=True)
    contactos_ext_total = fields.Integer(string='Extranjero — Total', readonly=True)
    contactos_ext_con_empresa = fields.Integer(string='Extranjero — Con RTN Empresa', readonly=True)
    contactos_ext_con_natural = fields.Integer(string='Extranjero — Con RTN Natural', readonly=True)
    contactos_ext_sin_empresa = fields.Integer(string='Extranjero — Sin RTN Empresa', readonly=True)
    contactos_ext_sin_natural = fields.Integer(string='Extranjero — Sin RTN Natural', readonly=True)
    contactos_sp_total = fields.Integer(string='Sin País — Total', readonly=True)
    contactos_sp_con_empresa = fields.Integer(string='Sin País — Con RTN Empresa', readonly=True)
    contactos_sp_con_natural = fields.Integer(string='Sin País — Con RTN Natural', readonly=True)
    contactos_sp_sin_empresa = fields.Integer(string='Sin País — Sin RTN Empresa', readonly=True)
    contactos_sp_sin_natural = fields.Integer(string='Sin País — Sin RTN Natural', readonly=True)

    base_gravada_ventas = fields.Monetary(
        string='Total Gravado Ventas',
        currency_field='currency_id',
        readonly=True,
        help='Suma de bases imponibles gravadas en ventas',
    )
    base_exenta_ventas = fields.Monetary(
        string='Total Exento Ventas',
        currency_field='currency_id',
        readonly=True,
        help='Ventas exentas de ISV',
    )
    base_exonerada_ventas = fields.Monetary(
        string='Total Exonerado Ventas',
        currency_field='currency_id',
        readonly=True,
        help='Ventas a clientes exonerados',
    )
    base_gravada_compras = fields.Monetary(
        string='Total Gravado Compras',
        currency_field='currency_id',
        readonly=True,
    )
    base_exenta_compras = fields.Monetary(
        string='Total Exento Compras',
        currency_field='currency_id',
        readonly=True,
    )
    base_exonerada_compras = fields.Monetary(
        string='Total Exonerado Compras',
        currency_field='currency_id',
        readonly=True,
    )
    total_facturado_bruto = fields.Monetary(
        string='Total Facturado Bruto',
        currency_field='currency_id',
        readonly=True,
        help='Gravado + Exento + Exonerado',
    )
    impuestos_detalle_html = fields.Html(
        string='Detalle por Impuesto',
        readonly=True,
        sanitize=False,
    )
    retenciones_detalle_html = fields.Html(
        string='Retenciones por Tipo',
        readonly=True,
        sanitize=False,
    )

    # ── Control de Zona Libre (ZOLI): límite de ventas locales ──
    es_zoli = fields.Boolean(
        related='company_id.es_zoli',
        readonly=True,
    )
    zoli_ventas_locales = fields.Monetary(
        string='Ventas Locales (Nacionalización) — Año',
        currency_field='currency_id',
        readonly=True,
    )
    zoli_ventas_exportacion = fields.Monetary(
        string='Ventas de Exportación — Año',
        currency_field='currency_id',
        readonly=True,
    )
    zoli_ventas_total = fields.Monetary(
        string='Ventas Totales — Año',
        currency_field='currency_id',
        readonly=True,
    )
    zoli_pct_local = fields.Float(
        string='% Ventas Locales',
        digits=(5, 2),
        readonly=True,
    )
    zoli_estado_limite = fields.Selection([
        ('ok', 'Dentro del límite'),
        ('alerta', 'Próximo al límite'),
        ('excedido', 'Límite excedido'),
    ], string='Estado Límite ZOLI', readonly=True)
    zoli_limite_html = fields.Html(
        string='Límite Ventas Locales ZOLI',
        readonly=True,
        sanitize=False,
    )

    def _compute_zoli_limite_local(self):
        """Acumulado anual de ventas locales vs total para empresa ZOLI."""
        self.ensure_one()
        if not self.company_id.es_zoli:
            self.zoli_ventas_locales = 0.0
            self.zoli_ventas_exportacion = 0.0
            self.zoli_ventas_total = 0.0
            self.zoli_pct_local = 0.0
            self.zoli_estado_limite = 'ok'
            self.zoli_limite_html = ''
            return

        year_start = (self.date_to or fields.Date.today()).replace(month=1, day=1)
        year_end = (self.date_to or fields.Date.today()).replace(month=12, day=31)
        facturas = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', year_start),
            ('invoice_date', '<=', year_end),
            ('company_id', '=', self.company_id.id),
        ])
        locales = facturas.filtered(
            lambda m: m.tipo_operacion_zoli == 'nacionalizacion')
        export = facturas.filtered(
            lambda m: m.tipo_operacion_zoli == 'exportacion')
        total_local = sum(locales.mapped('amount_untaxed'))
        total_export = sum(export.mapped('amount_untaxed'))
        total = sum(facturas.mapped('amount_untaxed'))

        self.zoli_ventas_locales = total_local
        self.zoli_ventas_exportacion = total_export
        self.zoli_ventas_total = total
        pct = (total_local / total * 100.0) if total else 0.0
        self.zoli_pct_local = pct

        limite = self.company_id.zoli_limite_local_pct or 50.0
        alerta = self.company_id.zoli_limite_alerta_pct or 45.0
        if pct > limite:
            self.zoli_estado_limite = 'excedido'
            color, label = 'danger', 'LÍMITE EXCEDIDO'
        elif pct >= alerta:
            self.zoli_estado_limite = 'alerta'
            color, label = 'warning', 'PRÓXIMO AL LÍMITE'
        else:
            self.zoli_estado_limite = 'ok'
            color, label = 'success', 'DENTRO DEL LÍMITE'

        simbolo = self.currency_id.symbol or 'L'
        self.zoli_limite_html = (
            f'<div class="alert alert-{color} mb-2">'
            f'<strong>Régimen Zona Libre — Ventas locales {year_start.year}: </strong>'
            f'<span class="fs-5 fw-bold">{pct:.2f}%</span> '
            f'(límite legal {limite:.0f}%) — {label}'
            f'</div>'
            f'<div class="progress mb-2" style="height:22px;">'
            f'<div class="progress-bar bg-{color}" role="progressbar" '
            f'style="width:{min(pct, 100):.1f}%;">{pct:.1f}%</div></div>'
            f'<table class="table table-sm mb-0">'
            f'<tr><td>Ventas locales (nacionalización)</td>'
            f'<td class="text-end fw-bold">{simbolo} {total_local:,.2f}</td></tr>'
            f'<tr><td>Ventas de exportación</td>'
            f'<td class="text-end">{simbolo} {total_export:,.2f}</td></tr>'
            f'<tr><td>Total ventas del año</td>'
            f'<td class="text-end fw-bold">{simbolo} {total:,.2f}</td></tr>'
            f'</table>'
        )

    def _get_company_fiscal_sequences(self):
        return self.env['ir.sequence'].search([
            ('is_fiscal', '=', True),
            ('company_id', '=', self.company_id.id),
        ])

    def _get_active_sequences(self):
        if self.all_sequences:
            return self._get_company_fiscal_sequences()
        return self.fiscal_sequence_ids

    def _should_filter_by_sequence(self):
        return not self.all_sequences and bool(self.fiscal_sequence_ids)

    def _get_journals_for_sequences(self, sequences, move_type='out_invoice'):
        if not sequences:
            return self.env['account.journal'].browse()
        Journal = self.env['account.journal']
        base = [('company_id', '=', self.company_id.id)]
        seq_ids = sequences.ids
        if move_type == 'out_invoice':
            return Journal.search(base + [('fiscal_sequence_id', 'in', seq_ids)])
        if move_type == 'out_refund':
            return Journal.search(
                base + [
                    '|',
                    ('fiscal_sequence_id', 'in', seq_ids),
                    ('refund_fiscal_sequence_id', 'in', seq_ids),
                ],
            )
        if move_type == 'in_invoice':
            return Journal.search(base + [('fiscal_sequence_id', 'in', seq_ids)])
        return Journal.search(
            base + [
                '|',
                ('fiscal_sequence_id', 'in', seq_ids),
                ('refund_fiscal_sequence_id', 'in', seq_ids),
            ],
        )

    def _filter_book_lines_by_sequence(self, lines, move_type='out_invoice'):
        if not self._should_filter_by_sequence():
            return lines
        journals = self._get_journals_for_sequences(
            self.fiscal_sequence_ids, move_type,
        )
        if not journals:
            return lines.browse()
        return lines.filtered(
            lambda line: line.invoice_id.journal_id in journals,
        )

    def _apply_move_domain_sequence_filter(self, domain, move_type='out_invoice'):
        if not self._should_filter_by_sequence():
            return domain
        journals = self._get_journals_for_sequences(
            self.fiscal_sequence_ids, move_type,
        )
        if journals:
            domain.append(('journal_id', 'in', journals.ids))
        else:
            domain.append(('id', '=', False))
        return domain

    @api.depends('date_to', 'obligado_dmc')
    def _compute_vencimiento_dmc_actual(self):
        BookPurchases = self.env['kc_fiscal_hn.book.purchases']
        today = fields.Date.context_today(self)
        for dash in self:
            if not dash.obligado_dmc or not dash.date_to:
                dash.fecha_vencimiento_dmc_mes = False
                dash.dias_vencimiento_dmc = 999
                continue
            venc = BookPurchases._calc_fecha_vencimiento_dmc(dash.date_to)
            dash.fecha_vencimiento_dmc_mes = venc
            dash.dias_vencimiento_dmc = (venc - today).days if venc else 999

    @api.depends('date_from', 'date_to', 'company_id', 'obligado_dmc')
    def _compute_estado_libro_mes(self):
        BookPurchases = self.env['kc_fiscal_hn.book.purchases']
        for dash in self:
            if not dash.obligado_dmc:
                dash.libro_mes_generado = False
                dash.libro_mes_declarado = False
                continue
            libro = BookPurchases.search([
                ('date_from', '=', dash.date_from),
                ('date_to', '=', dash.date_to),
                ('company_id', '=', dash.company_id.id),
            ], limit=1)
            dash.libro_mes_generado = bool(libro)
            dash.libro_mes_declarado = (
                libro.state == 'declared' if libro else False
            )

    @api.depends('date_from', 'date_to', 'company_id')
    def _compute_estado_consistencia(self):
        BookSales = self.env['kc_fiscal_hn.book.sales']
        BookPurchases = self.env['kc_fiscal_hn.book.purchases']
        for dash in self:
            libro_ventas = BookSales.search([
                ('date_from', '=', dash.date_from),
                ('date_to', '=', dash.date_to),
                ('company_id', '=', dash.company_id.id),
            ], limit=1)
            libro_compras = BookPurchases.search([
                ('date_from', '=', dash.date_from),
                ('date_to', '=', dash.date_to),
                ('company_id', '=', dash.company_id.id),
            ], limit=1)
            if not libro_ventas and not libro_compras:
                dash.estado_consistencia_periodo = 'sin_libros'
            elif (
                (libro_ventas and libro_ventas.consistencia_debito == 'diferencia')
                or (libro_compras and libro_compras.consistencia_isv == 'diferencia')
            ):
                dash.estado_consistencia_periodo = 'diferencia'
            elif (
                libro_ventas
                and libro_ventas.state == 'declared'
                and (not libro_compras or libro_compras.state == 'declared')
            ):
                dash.estado_consistencia_periodo = 'ok'
            else:
                dash.estado_consistencia_periodo = 'pendiente'

    def _get_book_header(self, model_name, date_from, date_to):
        return self.env[model_name].search([
            ('date_from', '=', date_from),
            ('date_to', '=', date_to),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

    def _get_book_lines(self, model_name, date_from, date_to):
        book = self._get_book_header(model_name, date_from, date_to)
        if not book or book.state != 'declared':
            line_model = f'{model_name}.line'
            if line_model in self.env:
                return self.env[line_model].browse()
            return self.env[model_name].browse()
        return book.line_ids

    @staticmethod
    def _is_period_declared(lines):
        if not lines:
            return False
        book = lines[:1].book_id
        return bool(book) and book.state == 'declared'

    @staticmethod
    def _declaration_meta(lines):
        book = lines[:1].book_id
        if not book:
            return False, ''
        return (
            book.fecha_declaracion,
            book.declarado_por.name if book.declarado_por else '',
        )

    def _get_live_invoices(self, date_from, date_to, move_type='out_invoice'):
        domain = [
            ('move_type', '=', move_type),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('company_id', '=', self.company_id.id),
        ]
        domain = self._apply_move_domain_sequence_filter(domain, move_type)
        return self.env['account.move'].search(domain)

    def _sales_from_book_lines(self, lines):
        fecha, declarado = self._declaration_meta(lines)
        book = lines[:1].book_id if lines else self.env['kc_fiscal_hn.book.sales']
        partners = lines.mapped('invoice_id.partner_id').filtered(lambda p: p)
        if partners:
            clientes = len(partners)
        else:
            clientes = len(set(filter(None, lines.mapped('rtn_cliente'))))
        total = book.total_general if book else sum(lines.mapped('amount_total'))
        return {
            'source': 'book',
            'declared': True,
            'fecha_declaracion': fecha,
            'declarado_por': declarado,
            'total': total,
            'count': len(lines.filtered(
                lambda l: l.tipo_documento == 'factura',
            )),
            'isv': sum(lines.mapped('isv_15')) + sum(lines.mapped('isv_18')),
            'isv15': sum(lines.mapped('isv_15')),
            'isv18': sum(lines.mapped('isv_18')),
            'exento': sum(lines.mapped('exento')),
            'exonerado': sum(lines.mapped('exonerado')),
            'clientes': clientes,
            'sin_rtn': len(lines.filtered(lambda l: not l.rtn_cliente)),
        }

    def _sales_from_invoices(self, facturas):
        return {
            'source': 'live',
            'declared': False,
            'fecha_declaracion': False,
            'declarado_por': '',
            'total': sum(facturas.mapped('amount_total')),
            'count': len(facturas),
            'isv': sum(facturas.mapped('isv_total')),
            'isv15': sum(facturas.mapped('amount_isv15')),
            'isv18': sum(facturas.mapped('amount_isv18')),
            'exento': sum(facturas.mapped('amount_exento')),
            'exonerado': sum(facturas.mapped('amount_exonerado')),
            'clientes': len(facturas.mapped('partner_id')),
            'sin_rtn': len(facturas.filtered(lambda m: not m.commercial_partner_id.vat)),
        }

    def _get_period_sales_data(self):
        lines = self._get_book_lines(
            'kc_fiscal_hn.book.sales',
            self.date_from,
            self.date_to,
        )
        lines = self._filter_book_lines_by_sequence(lines, 'out_invoice')
        if self._is_period_declared(lines):
            return self._sales_from_book_lines(lines)
        facturas = self._get_live_invoices(self.date_from, self.date_to)
        return self._sales_from_invoices(facturas)

    def _purchases_from_book_lines(self, lines):
        book = lines[:1].book_id if lines else self.env['kc_fiscal_hn.book.purchases']
        return {
            'source': 'book',
            'total': book.total_general if book else sum(lines.mapped('amount_total')),
            'count': len(lines.filtered(
                lambda l: l.tipo_documento == 'factura',
            )),
            'isv': sum(lines.mapped('isv_15')) + sum(lines.mapped('isv_18')),
        }

    def _purchases_from_invoices(self, facturas):
        return {
            'source': 'live',
            'total': sum(facturas.mapped('amount_total')),
            'count': len(facturas),
            'isv': sum(facturas.mapped('isv_total')),
        }

    def _get_period_purchases_data(self):
        lines = self._get_book_lines(
            'kc_fiscal_hn.book.purchases',
            self.date_from,
            self.date_to,
        )
        lines = self._filter_book_lines_by_sequence(lines, 'in_invoice')
        if self._is_period_declared(lines):
            return self._purchases_from_book_lines(lines)
        facturas = self._get_live_invoices(
            self.date_from, self.date_to, 'in_invoice',
        )
        return self._purchases_from_invoices(facturas)

    def _get_12_months_data(self):
        today = fields.Date.today()
        result = []
        for i in range(11, -1, -1):
            mes_inicio = (today - relativedelta(months=i)).replace(day=1)
            mes_fin = mes_inicio + relativedelta(months=1) - relativedelta(days=1)
            lines = self._get_book_lines(
                'kc_fiscal_hn.book.sales', mes_inicio, mes_fin,
            )
            if self._is_period_declared(lines):
                fecha, declarado = self._declaration_meta(lines)
                result.append({
                    'mes': mes_inicio.strftime('%b %Y'),
                    'total_ventas': (
                        lines[:1].book_id.total_general
                        if lines else 0.0
                    ),
                    'isv': sum(lines.mapped('isv_15')) + sum(lines.mapped('isv_18')),
                    'declarado': True,
                    'fecha_declaracion': str(fecha or ''),
                    'declarado_por': declarado,
                    'source': 'Libro SAR',
                })
            else:
                facturas = self._get_live_invoices(mes_inicio, mes_fin)
                result.append({
                    'mes': mes_inicio.strftime('%b %Y'),
                    'total_ventas': sum(facturas.mapped('amount_total')),
                    'isv': sum(facturas.mapped('isv_total')),
                    'declarado': False,
                    'fecha_declaracion': '',
                    'declarado_por': '',
                    'source': 'Tiempo Real',
                })
        return result

    def _generate_timeline_plotly(self):
        try:
            import plotly.graph_objects as go
            import plotly.offline as pyo
        except ImportError:
            return '<p class="text-warning">Plotly no disponible.</p>'

        data = self._get_12_months_data()
        labels = [d['mes'] for d in data]
        ventas = [d['total_ventas'] for d in data]
        isv = [d['isv'] for d in data]
        colores = ['#28a745' if d['declarado'] else '#ffc107' for d in data]
        hover = [
            (
                f"<b>{d['mes']}</b><br>"
                f"Ventas: L {d['total_ventas']:,.2f}<br>"
                f"ISV: L {d['isv']:,.2f}<br>"
                f"Declarado: {d['fecha_declaracion']}<br>"
                f"Por: {d['declarado_por']}"
            ) if d['declarado'] else (
                f"<b>{d['mes']}</b><br>"
                f"Ventas: L {d['total_ventas']:,.2f}<br>"
                f"ISV: L {d['isv']:,.2f}<br>"
                f"Pendiente de declarar"
            )
            for d in data
        ]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='Total Ventas',
            x=labels,
            y=ventas,
            marker_color=colores,
            text=['OK' if d['declarado'] else '...' for d in data],
            textposition='outside',
            hovertext=hover,
            hovertemplate='%{hovertext}<extra></extra>',
        ))
        fig.add_trace(go.Scatter(
            name='ISV',
            x=labels,
            y=isv,
            mode='lines+markers',
            line=dict(color='#dc3545', width=2),
            marker=dict(size=6),
            yaxis='y2',
            hovertemplate='<b>%{x}</b><br>ISV: L %{y:,.2f}<extra></extra>',
        ))
        fig.update_layout(
            title=dict(
                text=(
                    'Declaraciones SAR — Últimos 12 Meses'
                    '<br><sup>'
                    '<span style="color:#28a745">■</span> Declarado al SAR &nbsp;'
                    '<span style="color:#ffc107">■</span> Pendiente &nbsp;'
                    '<span style="color:#dc3545">—</span> ISV</sup>'
                ),
                x=0.5,
                xanchor='center',
            ),
            xaxis=dict(title='Período'),
            yaxis=dict(title='Total Ventas (L)', tickformat=',.0f'),
            yaxis2=dict(
                title='ISV (L)',
                overlaying='y',
                side='right',
                tickformat=',.0f',
            ),
            hovermode='x unified',
            legend=dict(orientation='h', x=0, y=1.12),
            height=420,
            margin=dict(l=70, r=70, t=100, b=60),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
        )
        return pyo.plot(
            fig,
            output_type='div',
            include_plotlyjs='cdn',
            config={
                'displayModeBar': True,
                'displaylogo': False,
                'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
            },
        )

    def _generate_dona_isv(self):
        try:
            import plotly.graph_objects as go
            import plotly.offline as pyo
        except ImportError:
            return ''

        labels = ['ISV 15%', 'ISV 18%', 'Exento', 'Exonerado']
        values = [
            self.isv_ventas_15,
            self.isv_ventas_18,
            self.ventas_exentas,
            self.ventas_exoneradas,
        ]
        colors = ['#ffc107', '#dc3545', '#6c757d', '#17a2b8']
        if not any(values):
            return '<p class="text-muted text-center">Sin datos</p>'

        fig = go.Figure(go.Pie(
            labels=labels,
            values=values,
            hole=0.5,
            marker_colors=colors,
            textinfo='label+percent',
            hovertemplate='<b>%{label}</b><br>L %{value:,.2f}<br>%{percent}<extra></extra>',
        ))
        fig.update_layout(
            title=dict(text='Distribución ISV', x=0.5, xanchor='center'),
            height=300,
            margin=dict(l=20, r=20, t=60, b=20),
            showlegend=True,
            legend=dict(orientation='h', x=0.5, xanchor='center', y=-0.15),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
        )
        return pyo.plot(
            fig,
            output_type='div',
            include_plotlyjs=False,
            config={'displayModeBar': False},
        )

    def _compute_secuencia_kpis(self):
        sequences = self._get_active_sequences()
        self.secuencias_seleccionadas = len(sequences)
        if not sequences:
            self.correlativos_usados = 0
            self.correlativos_disponibles = 0
            self.dias_vencimiento_cai = 0
            self.porcentaje_uso_secuencia = 0.0
            self.secuencias_status_html = (
                '<p class="text-muted mb-0">No hay secuencias fiscales configuradas.</p>'
            )
            return

        today = fields.Date.today()
        total_usados = total_disponibles = 0
        min_dias = False
        porcentajes = []
        rows = []

        for seq in sequences:
            current = seq._fiscal_active_date_ranges_on(today)
            if not current:
                rows.append(
                    f'<tr><td>{seq.display_name}</td>'
                    f'<td colspan="4" class="text-warning">Sin rango CAI vigente</td></tr>',
                )
                continue
            r = current[0]
            next_number = r.number_next_actual or r.number_next or r.rangoInicial
            usados = max(0, next_number - r.rangoInicial)
            disponibles = max(0, r.rangoFinal - next_number + 1)
            total_rango = max(1, r.rangoFinal - r.rangoInicial + 1)
            pct = usados / total_rango * 100
            dias = (r.date_to - today).days
            total_usados += usados
            total_disponibles += disponibles
            porcentajes.append(pct)
            min_dias = dias if min_dias is False else min(min_dias, dias)
            dias_class = 'text-danger' if dias <= 5 else 'text-warning' if dias <= 15 else ''
            rows.append(
                f'<tr>'
                f'<td><strong>{seq.display_name}</strong></td>'
                f'<td class="text-end">{usados:,}</td>'
                f'<td class="text-end text-success">{disponibles:,}</td>'
                f'<td class="text-end">{pct:.1f}%</td>'
                f'<td class="text-end {dias_class}">{dias}</td>'
                f'</tr>',
            )

        self.correlativos_usados = total_usados
        self.correlativos_disponibles = total_disponibles
        self.dias_vencimiento_cai = min_dias or 0
        self.porcentaje_uso_secuencia = (
            sum(porcentajes) / len(porcentajes) if porcentajes else 0.0
        )
        filtro = (
            'Todas las secuencias'
            if self.all_sequences
            else f'{len(self.fiscal_sequence_ids)} secuencia(s) seleccionada(s)'
        )
        self.secuencias_status_html = (
            f'<p class="small text-muted mb-2">Filtro activo: {filtro}</p>'
            f'<div class="table-responsive">'
            f'<table class="table table-sm table-hover mb-0">'
            f'<thead><tr>'
            f'<th>Secuencia</th><th class="text-end">Usados</th>'
            f'<th class="text-end">Disponibles</th><th class="text-end">% Uso</th>'
            f'<th class="text-end">Días CAI</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        )

    @staticmethod
    def _partner_rtn_counts(partners):
        return {
            'total': len(partners),
            'con_empresa': len(partners.filtered(lambda p: p.is_company and p.vat)),
            'con_natural': len(partners.filtered(
                lambda p: not p.is_company and p.vat,
            )),
            'sin_empresa': len(partners.filtered(
                lambda p: p.is_company and not p.vat,
            )),
            'sin_natural': len(partners.filtered(
                lambda p: not p.is_company and not p.vat,
            )),
        }

    def _assign_contacto_group(self, prefix, partners):
        counts = self._partner_rtn_counts(partners)
        setattr(self, f'contactos_{prefix}_total', counts['total'])
        setattr(self, f'contactos_{prefix}_con_empresa', counts['con_empresa'])
        setattr(self, f'contactos_{prefix}_con_natural', counts['con_natural'])
        setattr(self, f'contactos_{prefix}_sin_empresa', counts['sin_empresa'])
        setattr(self, f'contactos_{prefix}_sin_natural', counts['sin_natural'])

    def _compute_contactos_kpis(self):
        """Todos los contactos activos, desglosados HN / extranjero / sin país."""
        all_partners = self.env['res.partner'].search([
            ('active', '=', True),
            ('parent_id', '=', False),
        ])
        hn = self.env['res.country'].search([('code', '=', 'HN')], limit=1)
        sp_partners = all_partners.filtered(lambda p: not p.country_id)
        if hn:
            hn_partners = all_partners.filtered(lambda p: p.country_id == hn)
            ext_partners = all_partners - hn_partners - sp_partners
        else:
            hn_partners = all_partners.browse()
            ext_partners = all_partners - sp_partners

        self.contactos_total = len(all_partners)
        self._assign_contacto_group('hn', hn_partners)
        self._assign_contacto_group('ext', ext_partners)
        self._assign_contacto_group('sp', sp_partners)

    @staticmethod
    def _fiscal_product_lines(move):
        return move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
            or (not l.display_type and l.product_id),
        )

    def _compute_retenciones_detalle(self):
        """Desglose del monto de retención por tipo (impuesto de retención).

        Recorre las facturas de proveedor del período y agrupa por cada
        impuesto de retención (ISV 15%, ISR 12.5%, 1%, 10%, etc.), sumando
        la base y el monto retenido. Cubre todos los tipos de retención, no
        solo el total.
        """
        facturas_c = self._get_live_invoices(
            self.date_from, self.date_to, 'in_invoice',
        )

        detalle = {}
        for inv in facturas_c:
            for line in self._fiscal_product_lines(inv):
                for tax in line.tax_ids.filtered(
                    lambda t: t.is_retention
                    or getattr(t, 'tipo_impuesto', None) == 'retencion',
                ):
                    base = line.price_subtotal
                    if tax.amount_type == 'percent':
                        monto = abs(base * tax.amount / 100.0)
                    else:
                        monto = abs(tax.amount)
                    data = detalle.setdefault(tax.id, {
                        'nombre': tax.name,
                        'tasa': abs(tax.amount),
                        'codigo_sar': tax.codigo_sar or '',
                        'base': 0.0,
                        'monto': 0.0,
                        'lineas': 0,
                    })
                    data['base'] += base
                    data['monto'] += monto
                    data['lineas'] += 1

        currency_symbol = self.currency_id.symbol or 'L'

        def fmt(amount):
            return f'{currency_symbol} {amount:,.2f}'

        if not detalle:
            return (
                '<div class="text-center text-muted py-3">'
                'Sin retenciones aplicadas en el período.'
                '</div>'
            )

        filas = []
        total_base = total_monto = 0.0
        for data in sorted(
            detalle.values(), key=lambda d: d['monto'], reverse=True,
        ):
            total_base += data['base']
            total_monto += data['monto']
            codigo = (
                f'<span class="badge bg-dark me-1">{data["codigo_sar"]}</span>'
                if data['codigo_sar'] else ''
            )
            filas.append(
                '<tr>'
                f'<td>{codigo}{data["nombre"]}</td>'
                f'<td class="text-center">{data["tasa"]:.2f}%</td>'
                f'<td class="text-center">{data["lineas"]}</td>'
                f'<td class="text-end">{fmt(data["base"])}</td>'
                f'<td class="text-end fw-bold text-danger">'
                f'{fmt(data["monto"])}</td>'
                '</tr>'
            )

        return (
            '<table class="table table-sm table-hover mb-0">'
            '<thead class="table-dark"><tr>'
            '<th>Tipo de Retención</th>'
            '<th class="text-center">Tasa</th>'
            '<th class="text-center">Docs</th>'
            '<th class="text-end">Base</th>'
            '<th class="text-end">Retenido</th>'
            '</tr></thead>'
            f'<tbody>{"".join(filas)}</tbody>'
            '<tfoot><tr class="table-secondary fw-bold">'
            '<td colspan="3">Total</td>'
            f'<td class="text-end">{fmt(total_base)}</td>'
            f'<td class="text-end text-danger">{fmt(total_monto)}</td>'
            '</tr></tfoot>'
            '</table>'
        )

    def _compute_impuestos_detalle(self):
        """
        Desglose por impuesto leyendo dinámicamente account.tax.
        Separa ventas y compras según tasas configuradas en el sistema.
        """
        facturas_v = self._get_live_invoices(
            self.date_from, self.date_to, 'out_invoice',
        )
        facturas_c = self._get_live_invoices(
            self.date_from, self.date_to, 'in_invoice',
        )

        Tax = self.env['account.tax']
        company_domain = [
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
        ]
        impuestos_venta = Tax.search(
            company_domain + [
                ('tipo_impuesto', '=', 'isv'),
                ('type_tax_use', '=', 'sale'),
            ],
            order='amount asc',
        )
        impuestos_compra = Tax.search(
            company_domain + [
                ('tipo_impuesto', '=', 'isv'),
                ('type_tax_use', '=', 'purchase'),
            ],
            order='amount asc',
        )
        impuestos_especiales = Tax.search(
            company_domain + [
                ('tipo_impuesto', 'in', ['exento', 'exonerado']),
                ('type_tax_use', '=', 'sale'),
            ],
        )

        resultado_ventas = []
        resultado_compras = []

        for tax in impuestos_venta:
            base = isv = 0.0
            count = 0
            for inv in facturas_v:
                for line in self._fiscal_product_lines(inv):
                    if tax in line.tax_ids:
                        base += line.price_subtotal
                        if tax.amount > 0:
                            isv += line.price_subtotal * (tax.amount / 100)
                        count += 1
            if base > 0 or count > 0:
                resultado_ventas.append({
                    'nombre': tax.name,
                    'tasa': tax.amount,
                    'codigo_sar': tax.codigo_sar or '',
                    'base': base,
                    'isv': isv,
                    'lineas': count,
                    'tipo': tax.tipo_impuesto,
                })

        for tax in impuestos_especiales:
            base = 0.0
            count = 0
            for inv in facturas_v:
                for line in self._fiscal_product_lines(inv):
                    if tax in line.tax_ids:
                        base += line.price_subtotal
                        count += 1
            if base > 0:
                resultado_ventas.append({
                    'nombre': tax.name,
                    'tasa': 0,
                    'codigo_sar': tax.codigo_sar or '',
                    'base': base,
                    'isv': 0,
                    'lineas': count,
                    'tipo': tax.tipo_impuesto,
                })

        for tax in impuestos_compra:
            base = isv = 0.0
            count = 0
            for inv in facturas_c:
                for line in self._fiscal_product_lines(inv):
                    if tax in line.tax_ids:
                        base += line.price_subtotal
                        if tax.amount > 0:
                            isv += line.price_subtotal * (tax.amount / 100)
                        count += 1
            if base > 0 or count > 0:
                resultado_compras.append({
                    'nombre': tax.name,
                    'tasa': tax.amount,
                    'codigo_sar': tax.codigo_sar or '',
                    'base': base,
                    'isv': isv,
                    'lineas': count,
                    'tipo': tax.tipo_impuesto,
                })

        currency_symbol = self.currency_id.symbol or 'L'

        def fmt(amount):
            return f'{currency_symbol} {amount:,.2f}'

        def badge_tipo(tipo, tasa):
            colores = {
                'isv': 'warning' if tasa <= 15 else 'danger',
                'exento': 'secondary',
                'exonerado': 'info',
            }
            color = colores.get(tipo, 'dark')
            label = f'{tasa:.0f}%' if tasa > 0 else tipo.upper()
            return f'<span class="badge bg-{color}">{label}</span>'

        total_base_v = sum(r['base'] for r in resultado_ventas)
        total_isv_v = sum(r['isv'] for r in resultado_ventas)
        total_gravado_v = sum(
            r['base'] for r in resultado_ventas if r['tipo'] == 'isv'
        )
        total_exento_v = sum(
            r['base'] for r in resultado_ventas if r['tipo'] == 'exento'
        )
        total_exonerado_v = sum(
            r['base'] for r in resultado_ventas if r['tipo'] == 'exonerado'
        )
        total_base_c = sum(r['base'] for r in resultado_compras)
        total_isv_c = sum(r['isv'] for r in resultado_compras)

        html = '''
    <div class="row g-3">
        <div class="col-lg-7">
            <h6 class="fw-bold text-success mb-2">Impuestos Ventas</h6>
            <table class="table table-sm table-hover table-bordered mb-0">
                <thead class="table-success">
                    <tr>
                        <th>Impuesto</th>
                        <th>Cód SAR</th>
                        <th class="text-end">Base</th>
                        <th class="text-end">ISV</th>
                        <th class="text-end">Líneas</th>
                    </tr>
                </thead>
                <tbody>
        '''
        if resultado_ventas:
            for r in sorted(resultado_ventas, key=lambda x: -x['base']):
                html += f'''
                    <tr>
                        <td>{badge_tipo(r["tipo"], r["tasa"])} {r["nombre"]}</td>
                        <td class="text-muted small">{r["codigo_sar"]}</td>
                        <td class="text-end">{fmt(r["base"])}</td>
                        <td class="text-end fw-bold text-warning">{fmt(r["isv"])}</td>
                        <td class="text-end text-muted">{r["lineas"]}</td>
                    </tr>
                '''
        else:
            html += '''
                    <tr>
                        <td colspan="5" class="text-center text-muted">
                            Sin facturas en el período
                        </td>
                    </tr>
            '''

        html += f'''
                </tbody>
                <tfoot class="table-dark fw-bold">
                    <tr>
                        <td colspan="2">TOTAL VENTAS</td>
                        <td class="text-end">{fmt(total_base_v)}</td>
                        <td class="text-end text-warning">{fmt(total_isv_v)}</td>
                        <td></td>
                    </tr>
                </tfoot>
            </table>
        </div>
        <div class="col-lg-5">
            <h6 class="fw-bold text-primary mb-2">Impuestos Compras</h6>
            <table class="table table-sm table-hover table-bordered mb-0">
                <thead class="table-primary">
                    <tr>
                        <th>Impuesto</th>
                        <th class="text-end">Base</th>
                        <th class="text-end">ISV</th>
                    </tr>
                </thead>
                <tbody>
        '''
        if resultado_compras:
            for r in sorted(resultado_compras, key=lambda x: -x['base']):
                html += f'''
                    <tr>
                        <td>{badge_tipo(r["tipo"], r["tasa"])} {r["nombre"]}</td>
                        <td class="text-end">{fmt(r["base"])}</td>
                        <td class="text-end fw-bold text-info">{fmt(r["isv"])}</td>
                    </tr>
                '''
        else:
            html += '''
                    <tr>
                        <td colspan="3" class="text-center text-muted">
                            Sin compras en el período
                        </td>
                    </tr>
            '''

        isv_neto = total_isv_v - total_isv_c
        color_neto = 'danger' if isv_neto > 0 else 'success'
        label_neto = 'A PAGAR' if isv_neto > 0 else 'A FAVOR'

        html += f'''
                </tbody>
                <tfoot class="table-dark fw-bold">
                    <tr>
                        <td>TOTAL COMPRAS</td>
                        <td class="text-end">{fmt(total_base_c)}</td>
                        <td class="text-end text-info">{fmt(total_isv_c)}</td>
                    </tr>
                </tfoot>
            </table>
            <div class="alert alert-{color_neto} py-2 mt-2 text-center">
                <strong>ISV NETO {label_neto}:</strong>
                <span class="fs-5 fw-bold ms-2">{fmt(abs(isv_neto))}</span>
            </div>
        </div>
    </div>
    <div class="row g-3 mt-1">
        <div class="col-12">
            <div class="card border-0 bg-light">
                <div class="card-body py-2">
                    <div class="row text-center">
                        <div class="col-4">
                            <div class="text-muted small">Total Gravado</div>
                            <div class="fw-bold">{fmt(total_gravado_v)}</div>
                        </div>
                        <div class="col-4">
                            <div class="text-muted small">Total Exento</div>
                            <div class="fw-bold text-secondary">{fmt(total_exento_v)}</div>
                        </div>
                        <div class="col-4">
                            <div class="text-muted small">Total Exonerado</div>
                            <div class="fw-bold text-info">{fmt(total_exonerado_v)}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
        '''
        return html

    def action_select_all_sequences(self):
        self.ensure_one()
        sequences = self._get_company_fiscal_sequences()
        self.write({
            'all_sequences': True,
            'fiscal_sequence_ids': [(6, 0, sequences.ids)],
        })
        return self.action_compute_dashboard()

    def action_clear_sequence_filter(self):
        self.ensure_one()
        self.write({
            'all_sequences': True,
            'fiscal_sequence_ids': [(5, 0, 0)],
        })
        return self.action_compute_dashboard()

    @api.onchange('all_sequences')
    def _onchange_all_sequences(self):
        if self.all_sequences:
            sequences = self._get_company_fiscal_sequences()
            self.fiscal_sequence_ids = sequences

    @api.onchange('fiscal_sequence_ids')
    def _onchange_fiscal_sequence_ids(self):
        all_seq = self._get_company_fiscal_sequences()
        if not self.fiscal_sequence_ids:
            self.all_sequences = True
        elif len(self.fiscal_sequence_ids) >= len(all_seq):
            self.all_sequences = True
        else:
            self.all_sequences = False

    def action_compute_dashboard(self):
        self.ensure_one()

        sales = self._get_period_sales_data()
        purchases = self._get_period_purchases_data()

        if sales['source'] == purchases['source']:
            self.data_source = sales['source']
        else:
            self.data_source = 'mixed'

        self.periodo_declarado = sales['declared']
        self.fecha_declaracion = sales['fecha_declaracion']
        self.declarado_por = sales['declarado_por']
        self.total_ventas = sales['total']
        self.total_facturas_ventas = sales['count']
        self.isv_ventas = sales['isv']
        self.isv_ventas_15 = sales['isv15']
        self.isv_ventas_18 = sales['isv18']
        self.ventas_exentas = sales['exento']
        self.ventas_exoneradas = sales['exonerado']
        self.clientes_unicos = sales['clientes']
        self.facturas_sin_rtn = sales['sin_rtn']
        self.ticket_promedio = (
            sales['total'] / sales['count'] if sales['count'] > 0 else 0
        )

        self.total_facturas_compras = purchases['count']
        self.total_compras = purchases['total']
        self.isv_compras = purchases['isv']
        self.isv_neto_pagar = self.isv_ventas - self.isv_compras

        nc = self._get_live_invoices(self.date_from, self.date_to, 'out_refund')
        self.notas_credito = len(nc)
        self.monto_notas_credito = sum(nc.mapped('amount_total'))

        nd_domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('journal_id.document_fiscal', '=', 'debit'),
            ('company_id', '=', self.company_id.id),
        ]
        nd = self.env['account.move'].search(
            self._apply_move_domain_sequence_filter(nd_domain, 'out_invoice'),
        )
        self.notas_debito = len(nd)

        anuladas_domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'cancel'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]
        anuladas = self.env['account.move'].search(
            self._apply_move_domain_sequence_filter(anuladas_domain, 'out_invoice'),
        )
        self.facturas_anuladas = len(anuladas)

        guias = self.env['stock.picking'].search([
            ('state', '=', 'done'),
            ('date_done', '>=', self.date_from),
            ('date_done', '<=', self.date_to),
            ('sar_name', '!=', False),
            ('company_id', '=', self.company_id.id),
        ])
        self.guias_remision = len(guias)

        retenciones_domain = [
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('journal_id.document_fiscal', '=', 'retention'),
            ('company_id', '=', self.company_id.id),
        ]
        ret_lines = self.env['kc_fiscal_hn.book.retentions'].search([
            ('periodo_desde', '=', self.date_from),
            ('periodo_hasta', '=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ])
        if ret_lines:
            self.comprobantes_retencion = len(ret_lines)
            self.retenciones_aplicadas = sum(
                ret_lines.mapped('monto_retenido'),
            )
        else:
            retenciones = self.env['account.move'].search(
                self._apply_move_domain_sequence_filter(
                    retenciones_domain, 'in_invoice',
                ),
            )
            self.comprobantes_retencion = len(retenciones)
            self.retenciones_aplicadas = sum(
                retenciones.mapped('amount_total'),
            )

        facturas_v = self._get_live_invoices(
            self.date_from, self.date_to, 'out_invoice',
        )
        self.base_gravada_ventas = sum(
            facturas_v.mapped('base_imponible_total'),
        )
        self.base_exenta_ventas = sum(facturas_v.mapped('amount_exento'))
        self.base_exonerada_ventas = sum(
            facturas_v.mapped('amount_exonerado'),
        )
        self.total_facturado_bruto = (
            self.base_gravada_ventas
            + self.base_exenta_ventas
            + self.base_exonerada_ventas
        )

        facturas_c = self._get_live_invoices(
            self.date_from, self.date_to, 'in_invoice',
        )
        self.base_gravada_compras = sum(
            facturas_c.mapped('base_imponible_total'),
        )
        self.base_exenta_compras = sum(facturas_c.mapped('amount_exento'))
        self.base_exonerada_compras = sum(
            facturas_c.mapped('amount_exonerado'),
        )

        self._compute_secuencia_kpis()
        self._compute_contactos_kpis()
        self._compute_zoli_limite_local()
        self.timeline_chart_html = self._generate_timeline_plotly()
        self.dona_isv_html = self._generate_dona_isv()
        self.impuestos_detalle_html = self._compute_impuestos_detalle()
        self.retenciones_detalle_html = self._compute_retenciones_detalle()
        self._compute_estado_consistencia()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Dashboard Fiscal SAR'),
            'res_model': 'kc_fiscal_hn.dashboard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'main',
            'view_id': self.env.ref(
                'kc_fiscal_hn_v18.view_fiscal_dashboard_form',
            ).id,
            'context': {
                **self.env.context,
                'create': False,
                'delete': False,
                'duplicate': False,
            },
        }

    @api.model
    def action_open_dashboard(self):
        dashboard = self._get_user_dashboard()
        return dashboard.action_compute_dashboard()

    def action_view_libro_ventas(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Libro de Ventas SAR',
            'res_model': 'kc_fiscal_hn.book.sales',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_view_libro_compras(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Libro de Compras SAR (DMC)',
            'res_model': 'kc_fiscal_hn.book.purchases',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_view_alertas(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Alertas Secuencias Fiscales',
            'res_model': 'kc_fiscal_hn.sequence.alert',
            'view_mode': 'list,form',
            'target': 'current',
            'domain': [('state', '=', 'active')],
        }
