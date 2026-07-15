# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .fiscal_period import (
    action_notify_and_open_list,
    check_fiscal_period,
    numero_factura_compras,
)

TIPO_SERVICIO_RETENCION = [
    ('transporte_carga', 'Transporte de Carga'),
    ('alquiler_local', 'Alquiler de Locales'),
    ('alquiler_maquinaria', 'Alquiler de Maquinaria/Equipo'),
    ('seguridad', 'Servicios de Seguridad'),
    ('limpieza', 'Servicios de Limpieza'),
    ('mantenimiento', 'Mantenimiento de Equipo'),
    ('otros_servicios', 'Otros Servicios'),
]


class BookRetentions(models.Model):
    """Libro de Retenciones SAR."""

    _name = 'kc_fiscal_hn.book.retentions'
    _description = 'Libro de Retenciones SAR'
    _inherit = ['kc.fiscal.book.mixin', 'mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc, numero_factura'

    numero_factura = fields.Char(string='N° Factura', index=True, tracking=True)
    rtn_proveedor = fields.Char(string='RTN Proveedor', tracking=True)
    proveedor = fields.Char(string='Proveedor', required=True, tracking=True)
    base_imponible = fields.Monetary(
        string='Base imponible',
        currency_field='currency_id',
        tracking=True,
    )
    tipo_retencion = fields.Char(string='Tipo retención', tracking=True)
    tipo_servicio_retencion = fields.Selection(
        TIPO_SERVICIO_RETENCION,
        string='Tipo de Servicio',
        required=True,
        default='otros_servicios',
        help='Tipo de servicio que generó la retención '
             'según Acuerdo DEI-215-2010.',
    )
    porcentaje_retencion = fields.Float(
        string='% Retención',
        default=15.0,
        tracking=True,
        help='Porcentaje de retención ISV (generalmente 15%).',
    )
    monto_retenido = fields.Monetary(
        string='Monto retenido',
        compute='_compute_monto_retenido',
        store=True,
        currency_field='currency_id',
        tracking=True,
    )
    tipo_contribuyente = fields.Selection(
        related='company_id.tipo_contribuyente',
        readonly=True,
    )
    es_agente_retencion = fields.Boolean(
        related='company_id.es_agente_retencion',
        readonly=True,
    )

    total_monto_retenido = fields.Monetary(
        string='Total Retenido (Período)',
        compute='_compute_period_totals',
        store=True,
        currency_field='currency_id',
    )
    retencion_declarada_isv = fields.Monetary(
        string='Retención Declarada en ISV',
        currency_field='currency_id',
        help='Monto de retenciones reportado en '
             'Declaración ISV. Debe coincidir con '
             'el total del libro.',
    )
    diferencia_retencion_isv = fields.Monetary(
        string='Diferencia ISV vs Libro',
        compute='_compute_diferencia_retencion',
        store=True,
        currency_field='currency_id',
    )
    consistencia_retencion = fields.Selection([
        ('ok', '✅ Consistente'),
        ('diferencia', '⚠️ Diferencia detectada'),
        ('sin_verificar', '— Sin verificar'),
    ], compute='_compute_diferencia_retencion',
       store=True,
    )

    fecha_vencimiento = fields.Date(
        string='Vencimiento Declaración',
        compute='_compute_fecha_vencimiento',
        store=True,
    )
    dias_para_vencer = fields.Integer(
        string='Días para Vencer',
        compute='_compute_dias_vencer',
    )
    alerta_vencimiento = fields.Selection([
        ('ok', 'En tiempo'),
        ('proximo', 'Próximo a vencer'),
        ('urgente', 'Urgente (≤3 días)'),
        ('vencido', 'Vencido'),
    ], compute='_compute_alerta_vencimiento',
       string='Alerta Vencimiento',
       store=True,
    )

    comprobante_entregado = fields.Boolean(
        string='Comprobante Entregado',
        default=False,
        tracking=True,
    )
    fecha_entrega_comprobante = fields.Date(
        string='Fecha de Entrega',
        tracking=True,
    )
    metodo_entrega = fields.Selection([
        ('fisico', 'Físico'),
        ('email', 'Email'),
        ('portal', 'Portal SAR'),
    ], string='Método de Entrega',
    )
    email_proveedor = fields.Char(
        related='move_id.partner_id.email',
        string='Email Proveedor',
        readonly=True,
    )

    @api.depends('base_imponible', 'porcentaje_retencion')
    def _compute_monto_retenido(self):
        for line in self:
            line.monto_retenido = (
                line.base_imponible * line.porcentaje_retencion / 100.0
            )

    @staticmethod
    def _calc_fecha_vencimiento(date_to):
        """8vo día hábil del mes siguiente al período."""
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

    @api.depends('periodo_hasta', 'es_agente_retencion')
    def _compute_fecha_vencimiento(self):
        for line in self:
            if not line.periodo_hasta or not line.es_agente_retencion:
                line.fecha_vencimiento = False
            else:
                line.fecha_vencimiento = self._calc_fecha_vencimiento(
                    line.periodo_hasta,
                )

    @api.depends('fecha_vencimiento')
    def _compute_dias_vencer(self):
        today = fields.Date.context_today(self)
        for line in self:
            if line.fecha_vencimiento:
                line.dias_para_vencer = (
                    line.fecha_vencimiento - today
                ).days
            else:
                line.dias_para_vencer = 999

    @api.depends('dias_para_vencer', 'es_agente_retencion', 'estado')
    def _compute_alerta_vencimiento(self):
        for line in self:
            if not line.es_agente_retencion or line.estado == 'declarado':
                line.alerta_vencimiento = 'ok'
                continue
            dias = line.dias_para_vencer
            if dias < 0:
                line.alerta_vencimiento = 'vencido'
            elif dias <= 3:
                line.alerta_vencimiento = 'urgente'
            elif dias <= 8:
                line.alerta_vencimiento = 'proximo'
            else:
                line.alerta_vencimiento = 'ok'

    def _period_key(self):
        self.ensure_one()
        return (
            self.company_id.id,
            self.periodo_desde,
            self.periodo_hasta,
        )

    @api.model
    def _period_totals_map(self, keys):
        totals = {}
        for company_id, date_from, date_to in keys:
            if not company_id or not date_from or not date_to:
                totals[(company_id, date_from, date_to)] = 0.0
                continue
            lines = self.search([
                ('company_id', '=', company_id),
                ('periodo_desde', '=', date_from),
                ('periodo_hasta', '=', date_to),
            ])
            totals[(company_id, date_from, date_to)] = sum(
                lines.mapped('monto_retenido'),
            )
        return totals

    @api.depends(
        'periodo_desde',
        'periodo_hasta',
        'company_id',
        'monto_retenido',
    )
    def _compute_period_totals(self):
        keys = {line._period_key() for line in self}
        totals = self._period_totals_map(keys)
        for line in self:
            line.total_monto_retenido = totals.get(line._period_key(), 0.0)

    @api.depends(
        'total_monto_retenido',
        'retencion_declarada_isv',
    )
    def _compute_diferencia_retencion(self):
        for book in self:
            if not book.retencion_declarada_isv:
                book.diferencia_retencion_isv = 0
                book.consistencia_retencion = 'sin_verificar'
                continue
            diff = abs(
                book.total_monto_retenido -
                book.retencion_declarada_isv,
            )
            book.diferencia_retencion_isv = diff
            book.consistencia_retencion = (
                'ok' if diff <= 1.0 else 'diferencia'
            )

    def _get_fiscal_locked_fields(self):
        return super()._get_fiscal_locked_fields() - frozenset({
            'comprobante_entregado',
            'fecha_entrega_comprobante',
            'metodo_entrega',
            'retencion_declarada_isv',
        })

    def write(self, vals):
        if (
            'retencion_declarada_isv' in vals
            and not self.env.context.get('skip_period_sync')
        ):
            all_lines = self.browse()
            for line in self:
                all_lines |= self.search([
                    ('company_id', '=', line.company_id.id),
                    ('periodo_desde', '=', line.periodo_desde),
                    ('periodo_hasta', '=', line.periodo_hasta),
                ])
            return all_lines.with_context(
                skip_period_sync=True,
            ).write(vals)
        return super().write(vals)

    @api.depends('numero_factura', 'proveedor')
    def _compute_display_name(self) -> None:
        for line in self:
            line.display_name = (
                f'{line.numero_factura or ""} — {line.proveedor or ""}'
            )

    @api.model
    def _infer_tipo_servicio_retencion(self, move) -> str:
        for line in move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product',
        ):
            product = line.product_id
            if (
                product
                and product.tipo_servicio_retencion
            ):
                return product.tipo_servicio_retencion
        return 'otros_servicios'

    @api.model
    def _retention_info(self, move) -> dict:
        base = 0.0
        tipo = 'N/A'
        amount = 0.0
        rate = 0.0
        for line in move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product',
        ):
            for tax in line.tax_ids.filtered(
                lambda t: t.is_retention
                or getattr(t, 'tipo_impuesto', None) == 'retencion',
            ):
                base_val = line.price_subtotal
                base += base_val
                tipo = tax.name or 'Retención'
                rate = abs(tax.amount)
                if tax.amount_type == 'percent':
                    amount += abs(base_val * tax.amount / 100.0)
                else:
                    amount += abs(tax.amount)
        return {
            'base_imponible': base,
            'tipo_retencion': tipo,
            'porcentaje_retencion': rate,
            'monto_retenido': amount,
        }

    @api.model
    def _prepare_from_move(self, move, date_from, date_to) -> dict | None:
        info = self._retention_info(move)
        if not info['monto_retenido']:
            return None
        numero = numero_factura_compras(move)
        if not numero:
            return None
        return {
            'company_id': move.company_id.id,
            'move_id': move.id,
            'fecha': move.invoice_date or move.date,
            'numero_factura': numero,
            'rtn_proveedor': move.commercial_partner_id.vat or '',
            'proveedor': move.commercial_partner_id.name or '',
            'base_imponible': info['base_imponible'],
            'tipo_retencion': info['tipo_retencion'],
            'tipo_servicio_retencion': self._infer_tipo_servicio_retencion(move),
            'porcentaje_retencion': info['porcentaje_retencion'] or 15.0,
            'periodo_desde': date_from,
            'periodo_hasta': date_to,
            'estado': 'pendiente',
        }

    @api.model
    def _period_domain(self, company, date_from, date_to):
        return [
            ('company_id', '=', company.id),
            ('periodo_desde', '=', date_from),
            ('periodo_hasta', '=', date_to),
        ]

    @api.model
    def _clear_invoice_links(self, lines):
        for line in lines:
            if line.move_id:
                line.move_id.write({
                    'in_libro_retenciones': False,
                    'libro_retenciones_id': False,
                })

    @api.model
    def _link_invoices(self, lines):
        for line in lines:
            if line.move_id:
                line.move_id.write({
                    'in_libro_retenciones': True,
                    'libro_retenciones_id': line.id,
                })

    @api.model
    def action_generar_desde_facturas(
        self, date_from, date_to, company_id=None, replace=False,
    ):
        check_fiscal_period(date_from, date_to)
        company = (
            self.env['res.company'].browse(company_id)
            if company_id else self.env.company
        )
        if not company.es_agente_retencion:
            raise UserError(_(
                'La empresa "%(empresa)s" no está configurada como '
                'agente de retención ISV.\n\n'
                'Solo los grandes contribuyentes retienen el 15%% ISV. '
                'Verifique la clasificación SAR en '
                'Ajustes → Empresas → Información SAR.',
                empresa=company.name,
            ))
        period_domain = self._period_domain(company, date_from, date_to)
        if replace:
            to_delete = self.with_context(
                skip_book_line_lock=True,
            ).search(period_domain)
            self._clear_invoice_links(to_delete)
            to_delete.unlink()

        moves = self.env['account.move'].search([
            ('company_id', '=', company.id),
            ('move_type', 'in', ('in_invoice', 'in_refund')),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('journal_id.type', '=', 'purchase'),
        ])
        existing = set(self.search(period_domain).mapped('move_id').ids)
        vals_list = []
        sin_retencion = 0
        sin_numero = 0
        for move in moves:
            if move.id in existing:
                continue
            info = self._retention_info(move)
            if not info['monto_retenido']:
                sin_retencion += 1
                continue
            vals = self._prepare_from_move(move, date_from, date_to)
            if vals:
                vals_list.append(vals)
            else:
                sin_numero += 1

        created = self.with_context(skip_book_line_lock=True).create(
            vals_list,
        ) if vals_list else self.browse()

        self._link_invoices(created)

        if not created and moves:
            raise UserError(_(
                'No se generaron líneas de retenciones.\n\n'
                'Hay %(n)s factura(s) de proveedor confirmada(s), pero:\n'
                '• %(sin_ret)s sin impuesto de retención ISV\n'
                '• %(sin_num)s sin numeración válida\n\n'
                'Verifique impuestos de retención en las facturas y '
                'el N° correlativo del proveedor en la pestaña SAR.',
                n=len(moves),
                sin_ret=sin_retencion,
                sin_num=sin_numero,
            ))

        return action_notify_and_open_list(
            self.env,
            self._name,
            period_domain,
            _('Libro de Retenciones'),
            _('Se generaron %s líneas.', len(created)),
            list_name=_('Libro de Retenciones SAR'),
        )

    def action_marcar_declarado(self):
        for line in self:
            if line.consistencia_retencion == 'diferencia':
                raise UserError(_(
                    'No puede declarar el libro.\n\n'
                    'Diferencia de L %(diff).2f entre '
                    'total retenido (L %(libro).2f) y '
                    'lo declarado en ISV (L %(isv).2f).\n\n'
                    'El SAR cruza estos valores.',
                    diff=line.diferencia_retencion_isv,
                    libro=line.total_monto_retenido,
                    isv=line.retencion_declarada_isv,
                ))
        return super().action_marcar_declarado()

    def action_exportar_excel(self):
        if not self:
            raise UserError(_('No hay líneas para exportar.'))
        headers = [
            'Fecha', 'N° Factura', 'RTN', 'Proveedor', 'Base imponible',
            'Tipo', 'Tipo Servicio', '%', 'Monto retenido', 'Estado',
            'Fecha declaración', 'Declarado por', 'Notas',
        ]
        estado_labels = dict(self._fields['estado'].selection)
        servicio_labels = dict(TIPO_SERVICIO_RETENCION)
        rows = [
            [
                str(l.fecha or ''), l.numero_factura or '',
                l.rtn_proveedor or '', l.proveedor or '',
                l.base_imponible, l.tipo_retencion or '',
                servicio_labels.get(l.tipo_servicio_retencion, ''),
                l.porcentaje_retencion, l.monto_retenido,
                estado_labels.get(l.estado, ''),
                str(l.fecha_declaracion or ''),
                l.declarado_por.name or '', l.notas_rectificacion or '',
            ]
            for l in self
        ]
        return self._export_book_excel('Libro_Retenciones_SAR', headers, rows)
