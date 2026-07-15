# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .book_sales import _export_book_excel
from .fiscal_period import (
    action_notify_and_reload,
    check_fiscal_period,
    month_bounds,
    numero_factura_compras,
)


class BookPurchases(models.Model):
    _name = 'kc_fiscal_hn.book.purchases'
    _description = 'Libro de Compras SAR Honduras (DMC)'
    _order = 'date_from desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(compute='_compute_name', store=True)
    date_from = fields.Date(string='Fecha Desde', required=True, tracking=True)
    date_to = fields.Date(string='Fecha Hasta', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('pending', 'Pendiente'),
        ('declared', 'Declarado'),
        ('rectified', 'Rectificado'),
    ], default='draft', tracking=True)
    fecha_declaracion = fields.Date(readonly=True, tracking=True)
    declarado_por = fields.Many2one('res.users', readonly=True, tracking=True)
    notas_rectificacion = fields.Text(tracking=True)
    line_ids = fields.One2many(
        'kc_fiscal_hn.book.purchases.line',
        'book_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )

    total_compras = fields.Monetary(
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_nc_recibidas = fields.Monetary(
        string='Total NC Recibidas',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_nd_recibidas = fields.Monetary(
        string='Total ND Recibidas',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_isv_credito = fields.Monetary(
        string='Total ISV Crédito Fiscal',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_general = fields.Monetary(
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )

    modo_dmc = fields.Boolean(
        string='Modo DMC',
        compute='_compute_modo_dmc',
        store=True,
    )
    es_agente_retencion = fields.Boolean(
        string='Empresa es Agente Retención',
        compute='_compute_modo_dmc',
        store=True,
    )
    nivel_control = fields.Selection(
        related='company_id.nivel_control_fiscal',
        store=True,
        readonly=True,
    )
    fecha_vencimiento_dmc = fields.Date(
        string='Vencimiento DMC',
        compute='_compute_fecha_vencimiento_dmc',
        store=True,
    )
    dias_para_vencer = fields.Integer(
        string='Días para Vencer DMC',
        compute='_compute_dias_vencer',
    )
    alerta_vencimiento = fields.Selection([
        ('ok', 'En tiempo'),
        ('proximo', 'Próximo a vencer'),
        ('urgente', 'Urgente (≤3 días)'),
        ('vencido', 'Vencido'),
    ], compute='_compute_alerta_vencimiento', string='Alerta Vencimiento', store=True)

    total_fa_gravadas_15 = fields.Monetary(
        string='FA Gravadas 15%',
        compute='_compute_secciones_dmc',
        store=True,
        currency_field='currency_id',
    )
    total_fa_gravadas_18 = fields.Monetary(
        string='FA Gravadas 18%',
        compute='_compute_secciones_dmc',
        store=True,
        currency_field='currency_id',
    )
    total_oc_gravadas = fields.Monetary(
        string='OC (Otros Comprobantes)',
        compute='_compute_secciones_dmc',
        store=True,
        currency_field='currency_id',
    )
    total_exentas = fields.Monetary(
        string='Compras Exentas',
        compute='_compute_secciones_dmc',
        store=True,
        currency_field='currency_id',
    )
    total_exoneradas = fields.Monetary(
        string='Compras Exoneradas (OCE)',
        compute='_compute_secciones_dmc',
        store=True,
        currency_field='currency_id',
    )
    total_seccion_b = fields.Monetary(
        string='Sección B: Comprobantes Eventuales',
        compute='_compute_secciones_dmc',
        store=True,
        currency_field='currency_id',
        help='Compras eventuales de bienes y servicios: '
             'boletas de compra, proveedores ocasionales, '
             'personas naturales sin RTN.',
    )
    total_boletas_compra = fields.Monetary(
        string='Boletas de Compra',
        compute='_compute_secciones_dmc',
        store=True,
        currency_field='currency_id',
    )
    total_importaciones_15 = fields.Monetary(
        string='Importaciones Gravadas 15%',
        currency_field='currency_id',
    )
    total_importaciones_18 = fields.Monetary(
        string='Importaciones Gravadas 18%',
        currency_field='currency_id',
    )
    total_importaciones_exentas = fields.Monetary(
        string='Importaciones Exentas',
        currency_field='currency_id',
    )
    total_fyduca = fields.Monetary(
        string='FYDUCA (Guatemala)',
        currency_field='currency_id',
        help='Adquisiciones vía Factura y Declaración '
             'Única Centroamericana (FYDUCA)',
    )
    credito_fiscal_total = fields.Monetary(
        string='Total Crédito Fiscal',
        compute='_compute_credito_fiscal',
        store=True,
        currency_field='currency_id',
    )
    credito_declarado_isv = fields.Monetary(
        string='Crédito Fiscal Declarado en ISV',
        currency_field='currency_id',
        help='Ingrese el valor de la casilla 42 '
             'de su Declaración ISV del período. '
             'El sistema verificará consistencia '
             'con el crédito fiscal de la DMC.',
    )
    diferencia_isv_dmc = fields.Monetary(
        string='Diferencia ISV vs DMC',
        compute='_compute_diferencia_isv',
        store=True,
        currency_field='currency_id',
    )
    consistencia_isv = fields.Selection([
        ('ok', 'Consistente'),
        ('diferencia', 'Hay diferencia'),
        ('sin_verificar', 'Sin verificar'),
    ], string='Consistencia ISV/DMC',
       compute='_compute_diferencia_isv',
       store=True,
    )

    @staticmethod
    def _calc_fecha_vencimiento_dmc(date_to):
        """8vo día hábil del mes siguiente al período."""
        from datetime import timedelta
        if not date_to:
            return False
        if date_to.month == 12:
            primer_dia = date_to.replace(
                year=date_to.year + 1, month=1, day=1,
            )
        else:
            primer_dia = date_to.replace(
                month=date_to.month + 1, day=1,
            )
        dias_habiles = 0
        fecha = primer_dia
        while dias_habiles < 8:
            if fecha.weekday() < 5:
                dias_habiles += 1
            if dias_habiles < 8:
                fecha += timedelta(days=1)
        return fecha

    @api.depends('company_id.obligado_dmc', 'company_id.es_agente_retencion')
    def _compute_modo_dmc(self):
        for book in self:
            book.modo_dmc = book.company_id.obligado_dmc
            book.es_agente_retencion = book.company_id.es_agente_retencion

    @api.depends('date_to', 'modo_dmc')
    def _compute_fecha_vencimiento_dmc(self):
        for book in self:
            if not book.date_to or not book.modo_dmc:
                book.fecha_vencimiento_dmc = False
            else:
                book.fecha_vencimiento_dmc = (
                    self._calc_fecha_vencimiento_dmc(book.date_to)
                )

    @api.depends('fecha_vencimiento_dmc')
    def _compute_dias_vencer(self):
        today = fields.Date.context_today(self)
        for book in self:
            if book.fecha_vencimiento_dmc:
                book.dias_para_vencer = (
                    book.fecha_vencimiento_dmc - today
                ).days
            else:
                book.dias_para_vencer = 999

    @api.depends('dias_para_vencer', 'modo_dmc', 'state')
    def _compute_alerta_vencimiento(self):
        for book in self:
            if not book.modo_dmc or book.state == 'declared':
                book.alerta_vencimiento = 'ok'
                continue
            dias = book.dias_para_vencer
            if dias < 0:
                book.alerta_vencimiento = 'vencido'
            elif dias <= 3:
                book.alerta_vencimiento = 'urgente'
            elif dias <= 8:
                book.alerta_vencimiento = 'proximo'
            else:
                book.alerta_vencimiento = 'ok'

    @api.depends(
        'line_ids.seccion_dmc',
        'line_ids.gravado_15',
        'line_ids.gravado_18',
        'line_ids.exento',
        'line_ids.exonerado',
        'line_ids.amount_total',
        'line_ids.clase_documento',
    )
    def _compute_secciones_dmc(self):
        for book in self:
            sec_a = book.line_ids.filtered(
                lambda l: l.seccion_dmc == 'A',
            )
            sec_b = book.line_ids.filtered(
                lambda l: l.seccion_dmc == 'B',
            )
            book.total_fa_gravadas_15 = sum(sec_a.mapped('gravado_15'))
            book.total_fa_gravadas_18 = sum(sec_a.mapped('gravado_18'))
            book.total_oc_gravadas = sum(
                sec_a.filtered(
                    lambda l: l.clase_documento == 'OC',
                ).mapped('amount_total'),
            )
            book.total_exentas = sum(book.line_ids.mapped('exento'))
            book.total_exoneradas = sum(book.line_ids.mapped('exonerado'))
            book.total_seccion_b = sum(sec_b.mapped('amount_total'))
            book.total_boletas_compra = sum(
                sec_b.filtered(
                    lambda l: l.tipo_compra_dmc == 'boleta',
                ).mapped('amount_total'),
            )

    @api.depends(
        'credito_fiscal_total',
        'credito_declarado_isv',
    )
    def _compute_diferencia_isv(self):
        for book in self:
            if not book.credito_declarado_isv:
                book.diferencia_isv_dmc = 0
                book.consistencia_isv = 'sin_verificar'
                continue
            diff = abs(
                book.credito_fiscal_total - book.credito_declarado_isv,
            )
            book.diferencia_isv_dmc = diff
            book.consistencia_isv = (
                'ok' if diff <= 1.0 else 'diferencia'
            )

    @api.depends(
        'line_ids.isv_15',
        'line_ids.isv_18',
        'total_importaciones_15',
        'total_importaciones_18',
        'total_fyduca',
    )
    def _compute_credito_fiscal(self):
        for book in self:
            isv_local = (
                sum(book.line_ids.mapped('isv_15'))
                + sum(book.line_ids.mapped('isv_18'))
            )
            isv_importaciones = (
                book.total_importaciones_15 * 0.15
                + book.total_importaciones_18 * 0.18
            )
            book.credito_fiscal_total = isv_local + isv_importaciones

    @api.depends('date_from', 'date_to')
    def _compute_name(self):
        for book in self:
            if book.date_from:
                book.name = (
                    f'Libro Compras SAR '
                    f'{book.date_from.strftime("%B %Y")}'
                )
            else:
                book.name = 'Libro Compras SAR'

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
        'line_ids.tipo_documento',
        'line_ids.isv_15',
        'line_ids.isv_18',
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
            book.total_compras = sum(facturas.mapped('amount_total'))
            book.total_nc_recibidas = sum(nc.mapped('amount_total'))
            book.total_nd_recibidas = sum(nd.mapped('amount_total'))
            book.total_isv_credito = (
                sum(book.line_ids.mapped('isv_15'))
                + sum(book.line_ids.mapped('isv_18'))
            )
            book.total_general = (
                book.total_compras
                + book.total_nd_recibidas
                - book.total_nc_recibidas
            )

    @staticmethod
    def _tipo_documento_from_move(move):
        if move.move_type == 'in_refund':
            return 'nota_credito'
        if move.journal_id.document_fiscal == 'debit':
            return 'nota_debito'
        return 'factura'

    @staticmethod
    def _seccion_dmc_para_libro(move):
        """Sección DMC usable en libro (fallback para diarios sin clasificar)."""
        seccion = move.seccion_dmc
        if seccion == 'NA' and move.move_type in ('in_invoice', 'in_refund'):
            if move.journal_id.type == 'purchase':
                return 'A'
            return None
        return seccion if seccion != 'NA' else None

    @staticmethod
    def _numero_factura_libro(move):
        return numero_factura_compras(move)

    def _libro_proveedor_partner(self, move, expense=None):
        """Partner fiscal para RTN/nombre en libro de compras."""
        return move.commercial_partner_id

    def _iter_libro_compras_sources(self, move):
        """Fuentes (expense opcional) que generan líneas del libro por move."""
        yield None

    def _libro_numero_documento(self, move, expense=None):
        return self._numero_factura_libro(move)

    def _libro_line_amounts(self, move, expense=None):
        """Montos SAR de una línea del libro (move completo por defecto)."""
        costo = gasto = no_deducible = 0.0
        if move.montos_sar == 'costo':
            costo = move.amount_total
        elif move.montos_sar == 'gasto':
            gasto = move.amount_total
        elif move.montos_sar == 'no_deducible':
            no_deducible = move.amount_total
        return {
            'exento': move.amount_exento,
            'exonerado': move.amount_exonerado,
            'gravado_15': move.gravado_isv15,
            'isv_15': move.amount_isv15,
            'gravado_18': move.gravado_isv18,
            'isv_18': move.amount_isv18,
            'amount_total': move.amount_total,
            'costo': costo,
            'gasto': gasto,
            'no_deducible': no_deducible,
            'clase_documento': move.class_document_sar or 'FA',
            'cai_proveedor': move.cai_proveedor or '',
            'fecha_emision': move.femision_proveedor or '',
            'tipo_compra_dmc': (
                move.tipo_compra_dmc
                if move.tipo_compra_dmc and move.tipo_compra_dmc != 'na'
                else 'fa_gravada_15'
            ),
        }

    def _prepare_purchase_book_line_vals(self, move, seccion, expense=None):
        partner = self._libro_proveedor_partner(move, expense=expense)
        amounts = self._libro_line_amounts(move, expense=expense)
        if move.move_type == 'in_refund':
            tipo_doc = 'nota_credito'
        elif move.journal_id.document_fiscal == 'debit':
            tipo_doc = 'nota_debito'
        else:
            tipo_doc = 'factura'
        numero = self._libro_numero_documento(move, expense=expense)
        if not numero:
            return None
        return {
            'book_id': self.id,
            'fecha': move.invoice_date,
            'rtn_proveedor': partner.vat or '',
            'proveedor': partner.name,
            'clase_documento': amounts['clase_documento'],
            'cai_proveedor': amounts['cai_proveedor'],
            'numero_factura': numero,
            'fecha_emision': amounts['fecha_emision'],
            'exento': amounts['exento'],
            'exonerado': amounts['exonerado'],
            'gravado_15': amounts['gravado_15'],
            'isv_15': amounts['isv_15'],
            'gravado_18': amounts['gravado_18'],
            'isv_18': amounts['isv_18'],
            'amount_total': amounts['amount_total'],
            'tipo_documento': tipo_doc,
            'seccion_dmc': seccion,
            'tipo_compra_dmc': amounts['tipo_compra_dmc'],
            'numero_dua': move.numero_dua or '',
            'costo': amounts['costo'],
            'gasto': amounts['gasto'],
            'no_deducible': amounts['no_deducible'],
            'invoice_id': move.id,
        }

    @api.model
    def action_generar_desde_facturas(
        self, date_from, date_to, company_id=None, replace=False,
    ):
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
            ('move_type', 'in', ['in_invoice', 'in_refund']),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('journal_id.type', '=', 'purchase'),
        ]
        moves = self.env['account.move'].search(
            domain, order='invoice_date asc',
        )

        lines_vals = []
        for move in moves:
            seccion = self._seccion_dmc_para_libro(move)
            if not seccion:
                continue
            for expense in self._iter_libro_compras_sources(move):
                line_vals = self._prepare_purchase_book_line_vals(
                    move, seccion, expense=expense,
                )
                if line_vals:
                    lines_vals.append(line_vals)

        self.env['kc_fiscal_hn.book.purchases.line'].with_context(
            skip_book_line_lock=True,
        ).sudo().create(lines_vals)

        moves_in_book = moves.filtered(
            lambda move: any(
                line_vals['invoice_id'] == move.id for line_vals in lines_vals
            ),
        )
        for move in moves_in_book:
            move.write({
                'in_libro_compras': True,
                'libro_compras_id': self.id,
            })

        self.state = 'pending'

        n_fact = len([v for v in lines_vals if v['tipo_documento'] == 'factura'])
        n_nc = len([v for v in lines_vals if v['tipo_documento'] == 'nota_credito'])
        n_nd = len([v for v in lines_vals if v['tipo_documento'] == 'nota_debito'])

        if not lines_vals and moves:
            raise UserError(_(
                'No se pudieron generar líneas del libro de compras.\n\n'
                'Hay %(n)s factura(s) de proveedor confirmada(s) en el '
                'período, pero ninguna cumple los requisitos SAR '
                '(numeración válida y clasificación DMC).\n\n'
                'Revise la pestaña SAR de cada factura y configure el '
                'diario de compras con Documento Fiscal = '
                '«Factura Proveedor (FA)».',
                n=len(moves),
            ))

        return action_notify_and_reload(
            self,
            _('Libro Generado'),
            _(
                '%d líneas generadas (%d facturas, %d NC, %d ND).',
                len(lines_vals), n_fact, n_nc, n_nd,
            ),
        )

    def action_declare(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('El libro no tiene líneas.'))
        if (
            self.modo_dmc
            and self.consistencia_isv == 'diferencia'
        ):
            raise UserError(_(
                'No puede declarar el libro.\n\n'
                'Hay una diferencia de L %(diff).2f '
                'entre el crédito fiscal de la DMC '
                '(L %(dmc).2f) y el valor declarado '
                'en ISV casilla 42 (L %(isv).2f).\n\n'
                'El SAR cruza automáticamente estos '
                'valores. Corrija antes de declarar.',
                diff=self.diferencia_isv_dmc,
                dmc=self.credito_fiscal_total,
                isv=self.credito_declarado_isv,
            ))
        self.write({
            'state': 'declared',
            'fecha_declaracion': fields.Date.context_today(self),
            'declarado_por': self.env.user.id,
        })

    def action_rectify(self):
        self.ensure_one()
        if not self.notas_rectificacion:
            raise UserError(_('Ingrese notas de rectificación.'))
        self.write({'state': 'rectified'})

    def _clear_book(self):
        for line in self.line_ids:
            if line.invoice_id:
                line.invoice_id.write({
                    'in_libro_compras': False,
                    'libro_compras_id': False,
                })
        self.line_ids.with_context(skip_book_line_lock=True).sudo().unlink()

    def action_export_excel(self):
        self.ensure_one()
        return self.action_exportar_excel()

    def action_exportar_excel(self):
        if not self.line_ids:
            raise UserError(_('No hay líneas para exportar.'))
        headers = [
            'Fecha', 'RTN', 'Proveedor', 'Clase', 'CAI', 'N° Factura',
            'Tipo', 'Exento', 'Exonerado', 'Gravado 15%', 'ISV 15%',
            'Gravado 18%', 'ISV 18%', 'Costo', 'Gasto', 'No deducible',
            'Total',
        ]
        tipo_labels = dict(
            self.env['kc_fiscal_hn.book.purchases.line']
            ._fields['tipo_documento'].selection
        )
        rows = []
        for line in self.line_ids:
            rows.append([
                str(line.fecha or ''),
                line.rtn_proveedor or '',
                line.proveedor or '',
                line.clase_documento or '',
                line.cai_proveedor or '',
                line.numero_factura or '',
                tipo_labels.get(line.tipo_documento, ''),
                line.exento,
                line.exonerado,
                line.gravado_15,
                line.isv_15,
                line.gravado_18,
                line.isv_18,
                line.costo,
                line.gasto,
                line.no_deducible,
                line.amount_total,
            ])
        return _export_book_excel(self, 'Libro_Compras_DMC', headers, rows)


class BookPurchasesLine(models.Model):
    _name = 'kc_fiscal_hn.book.purchases.line'
    _description = 'Línea Libro de Compras SAR'
    _order = 'fecha asc'
    _inherit = ['kc.fiscal.book.line.mixin']

    book_id = fields.Many2one(
        'kc_fiscal_hn.book.purchases',
        required=True,
        ondelete='cascade',
    )
    invoice_id = fields.Many2one(
        'account.move',
        readonly=True,
        ondelete='set null',
    )
    tipo_documento = fields.Selection([
        ('factura', 'Factura'),
        ('nota_credito', 'NC Recibida'),
        ('nota_debito', 'ND Recibida'),
    ], default='factura', readonly=True)
    fecha = fields.Date(required=True, readonly=True)
    rtn_proveedor = fields.Char(string='RTN Proveedor', readonly=True)
    proveedor = fields.Char(required=True, readonly=True)
    clase_documento = fields.Char(string='Clase Doc.', readonly=True)
    seccion_dmc = fields.Selection([
        ('A', 'A — Compras Locales'),
        ('B', 'B — Eventuales'),
        ('C', 'C — Importaciones'),
    ], string='Sección DMC', default='A', readonly=True)
    tipo_compra_dmc = fields.Selection([
        ('fa_gravada_15', 'FA Gravada 15%'),
        ('fa_gravada_18', 'FA Gravada 18%'),
        ('fa_exenta', 'FA Exenta'),
        ('fa_exonerada', 'FA Exonerada'),
        ('oc_gravada', 'OC Gravada'),
        ('oc_exenta', 'OC Exenta'),
        ('boleta', 'Boleta de Compra'),
        ('importacion_15', 'Importación 15%'),
        ('importacion_18', 'Importación 18%'),
        ('importacion_exenta', 'Importación Exenta'),
        ('fyduca', 'FYDUCA Guatemala'),
    ], string='Tipo DMC', readonly=True)
    numero_dua = fields.Char(string='N° DUA', readonly=True)
    cai_proveedor = fields.Char(string='CAI Proveedor', readonly=True)
    numero_factura = fields.Char(string='N° Factura', readonly=True)
    fecha_emision = fields.Char(string='Fecha Emisión', readonly=True)
    exento = fields.Monetary(currency_field='currency_id', readonly=True)
    exonerado = fields.Monetary(currency_field='currency_id', readonly=True)
    gravado_15 = fields.Monetary(
        string='Gravado 15%',
        currency_field='currency_id',
        readonly=True,
    )
    isv_15 = fields.Monetary(
        string='ISV 15%',
        currency_field='currency_id',
        readonly=True,
    )
    gravado_18 = fields.Monetary(
        string='Gravado 18%',
        currency_field='currency_id',
        readonly=True,
    )
    isv_18 = fields.Monetary(
        string='ISV 18%',
        currency_field='currency_id',
        readonly=True,
    )
    costo = fields.Monetary(currency_field='currency_id', readonly=True)
    gasto = fields.Monetary(currency_field='currency_id', readonly=True)
    no_deducible = fields.Monetary(
        string='No Deducible',
        currency_field='currency_id',
        readonly=True,
    )
    amount_total = fields.Monetary(
        string='Total',
        currency_field='currency_id',
        readonly=True,
    )
    state = fields.Selection(related='book_id.state', store=True)
    currency_id = fields.Many2one(
        'res.currency',
        related='book_id.currency_id',
    )
