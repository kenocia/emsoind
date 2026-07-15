# -*- coding: utf-8 -*-

import operator as operator_module
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockLot(models.Model):
    """Control legal de permanencia de materia prima bajo régimen de Zona Libre.

    El DUCA (Declaración Única Centroamericana) se registra como un lote de la
    materia prima importada. Cada lote DUCA tiene una fecha de ingreso y una
    fecha de vencimiento (ingreso + días de permanencia de la compañía), y queda
    sujeto a alertas y a bloqueo de uso una vez vencido.
    """
    _inherit = 'stock.lot'

    # ── Datos del DUCA ────────────────────────────────────────
    duca_number = fields.Char(
        string='Número DUCA',
        index=True,
        copy=False,
        help='Número de la Declaración Única Centroamericana (DUCA) con la que '
             'ingresó esta materia prima bajo régimen de Zona Libre.',
    )
    duca_fecha_ingreso = fields.Date(
        string='Fecha de Ingreso DUCA',
        copy=False,
        help='Fecha de recepción de la materia prima importada. Base para el '
             'cálculo de la fecha de vencimiento de permanencia.',
    )
    duca_fecha_vencimiento = fields.Date(
        string='Fecha de Vencimiento DUCA',
        compute='_compute_duca_fecha_vencimiento',
        store=True,
        help='Fecha límite de permanencia bajo Zona Libre: fecha de ingreso + '
             'días de permanencia configurados en la compañía.',
    )
    duca_documento = fields.Binary(
        string='Documento DUCA',
        attachment=True,
        copy=False,
        help='Fotografía o escaneo del documento DUCA adjunto en la recepción.',
    )
    duca_documento_filename = fields.Char(
        string='Nombre del Documento DUCA',
        copy=False,
    )

    # ── Estado / control de permanencia ───────────────────────
    es_duca = fields.Boolean(
        string='Sujeto a control DUCA',
        compute='_compute_es_duca',
        store=True,
        help='Verdadero si el lote corresponde a materia prima importada bajo '
             'control DUCA en una compañía ZOLI.',
    )
    duca_dias_para_vencer = fields.Integer(
        string='Días para vencer (DUCA)',
        compute='_compute_duca_estado',
        store=True,
    )
    duca_estado = fields.Selection([
        ('na', 'No aplica'),
        ('vigente', 'Vigente'),
        ('proximo', 'Próximo a vencer'),
        ('critico', 'Crítico'),
        ('vencido', 'Vencido'),
    ], string='Estado DUCA',
       compute='_compute_duca_estado',
       store=True,
    )
    duca_stock_disponible = fields.Float(
        string='Stock Disponible (DUCA)',
        compute='_compute_duca_stock_disponible',
        search='_search_duca_stock_disponible',
        digits='Product Unit of Measure',
        help='Cantidad físicamente disponible de este lote en ubicaciones '
             'internas.',
    )

    # ── Autorización de uso de lotes vencidos ─────────────────
    duca_autorizado_vencido = fields.Boolean(
        string='Uso de vencido autorizado',
        copy=False,
        help='Si está activo, gerencia autorizó expresamente el uso de este '
             'lote a pesar de estar vencido.',
    )
    duca_autorizado_por_id = fields.Many2one(
        'res.users',
        string='Autorizado por',
        copy=False,
        readonly=True,
    )
    duca_fecha_autorizacion = fields.Datetime(
        string='Fecha de Autorización',
        copy=False,
        readonly=True,
    )
    duca_motivo_autorizacion = fields.Text(
        string='Motivo de Autorización',
        copy=False,
    )

    # ── Nacionalización (cierre del DUCA) ─────────────────────
    duca_cantidad_nacionalizada = fields.Float(
        string='Cantidad Nacionalizada',
        digits='Product Unit of Measure',
        copy=False,
        default=0.0,
        help='Cantidad de este lote que ya fue nacionalizada (importación '
             'definitiva) y por tanto salió del régimen de Zona Libre.',
    )

    @api.depends('product_id', 'product_id.requiere_control_duca',
                 'company_id', 'company_id.es_zoli')
    def _compute_es_duca(self):
        for lot in self:
            company = lot.company_id or self.env.company
            lot.es_duca = bool(
                company.es_zoli and lot.product_id.requiere_control_duca
            )

    @api.depends('duca_fecha_ingreso', 'company_id',
                 'company_id.duca_dias_permanencia')
    def _compute_duca_fecha_vencimiento(self):
        for lot in self:
            company = lot.company_id or self.env.company
            dias = company.duca_dias_permanencia or 180
            if lot.duca_fecha_ingreso:
                lot.duca_fecha_vencimiento = (
                    lot.duca_fecha_ingreso + timedelta(days=dias)
                )
            else:
                lot.duca_fecha_vencimiento = False

    @api.depends('es_duca', 'duca_fecha_vencimiento', 'company_id',
                 'company_id.duca_dias_alerta_previa',
                 'company_id.duca_dias_alerta_critica')
    def _compute_duca_estado(self):
        today = fields.Date.context_today(self)
        for lot in self:
            if not lot.es_duca or not lot.duca_fecha_vencimiento:
                lot.duca_estado = 'na'
                lot.duca_dias_para_vencer = 0
                continue
            company = lot.company_id or self.env.company
            dias_previa = company.duca_dias_alerta_previa or 30
            dias_critica = company.duca_dias_alerta_critica or 7
            dias = (lot.duca_fecha_vencimiento - today).days
            lot.duca_dias_para_vencer = dias
            if dias < 0:
                lot.duca_estado = 'vencido'
            elif dias <= dias_critica:
                lot.duca_estado = 'critico'
            elif dias <= dias_previa:
                lot.duca_estado = 'proximo'
            else:
                lot.duca_estado = 'vigente'

    def _compute_duca_stock_disponible(self):
        for lot in self:
            quants = self.env['stock.quant'].search([
                ('lot_id', '=', lot.id),
                ('location_id.usage', '=', 'internal'),
            ])
            lot.duca_stock_disponible = sum(quants.mapped('quantity'))

    def _search_duca_stock_disponible(self, operator, value):
        supported = {
            '=': operator_module.eq,
            '!=': operator_module.ne,
            '<': operator_module.lt,
            '<=': operator_module.le,
            '>': operator_module.gt,
            '>=': operator_module.ge,
        }
        if operator not in supported:
            raise UserError(_(
                'Operador no soportado para "Stock Disponible (DUCA)".'))
        compare = supported[operator]
        groups = self.env['stock.quant']._read_group(
            [('location_id.usage', '=', 'internal'), ('lot_id', '!=', False)],
            groupby=['lot_id'],
            aggregates=['quantity:sum'],
        )
        lot_ids = [lot.id for lot, qty in groups if compare(qty, value)]
        return [('id', 'in', lot_ids)]

    def action_autorizar_uso_vencido(self):
        """Gerencia autoriza el uso de un lote DUCA vencido."""
        if not self.env.user.has_group(
                'kc_fiscal_hn_v18.group_zoli_gerencia'):
            raise UserError(_(
                'Solo Gerencia de Zona Libre puede autorizar el uso de lotes '
                'DUCA vencidos.'))
        self.write({
            'duca_autorizado_vencido': True,
            'duca_autorizado_por_id': self.env.user.id,
            'duca_fecha_autorizacion': fields.Datetime.now(),
        })
        for lot in self:
            lot.message_post(body=_(
                'Uso de lote vencido AUTORIZADO por %(user)s.',
                user=self.env.user.name,
            ))
        return True

    def _check_duca_no_vencido(self, document=None):
        """Valida que los lotes DUCA no estén vencidos al usarse en una salida.

        Aplica el modo configurado en la compañía (advertencia o bloqueo).
        Los lotes con autorización expresa de gerencia siempre pasan.
        """
        es_gerente = self.env.user.has_group(
            'kc_fiscal_hn_v18.group_zoli_gerencia')
        bloqueados = []
        for lot in self:
            if not lot.es_duca or lot.duca_estado != 'vencido':
                continue
            if lot.duca_autorizado_vencido or es_gerente:
                continue
            company = lot.company_id or self.env.company
            if company.duca_modo_vencidos == 'advertencia':
                lot.message_post(body=_(
                    'ADVERTENCIA: se utilizó el lote DUCA vencido %(lote)s '
                    '(venció el %(fecha)s).',
                    lote=lot.name,
                    fecha=lot.duca_fecha_vencimiento,
                ))
                continue
            bloqueados.append(_(
                '- %(lote)s (DUCA %(duca)s): venció el %(fecha)s',
                lote=lot.name,
                duca=lot.duca_number or '-',
                fecha=lot.duca_fecha_vencimiento,
            ))
        if bloqueados:
            raise UserError(_(
                'No es posible usar materia prima con lotes DUCA vencidos sin '
                'autorización expresa de gerencia:\n\n%(lotes)s\n\n'
                'Solicite a Gerencia de Zona Libre la autorización del lote, o '
                'utilice un lote vigente.',
                lotes='\n'.join(bloqueados),
            ))

    @api.model
    def _cron_duca_alertas(self):
        """Cron diario: alertas de vencimiento de lotes DUCA por compañía ZOLI.

        - A 'duca_dias_alerta_previa' días: actividad a compras y bodega.
        - A 'duca_dias_alerta_critica' días: actividad crítica + correo.
        - Vencidos: actividad de vencimiento.
        Es idempotente: no duplica actividades abiertas del mismo tipo.
        """
        today = fields.Date.context_today(self)
        companies = self.env['res.company'].search([('es_zoli', '=', True)])
        # Refresca el estado almacenado (depende del día actual).
        todos = self.search([
            ('es_duca', '=', True),
            ('company_id', 'in', companies.ids),
        ])
        todos._compute_duca_estado()
        for company in companies:
            dias_previa = company.duca_dias_alerta_previa or 30
            limite = today + timedelta(days=dias_previa)
            lots = self.search([
                ('company_id', '=', company.id),
                ('es_duca', '=', True),
                ('duca_fecha_vencimiento', '!=', False),
                ('duca_fecha_vencimiento', '<=', limite),
            ])
            for lot in lots:
                if lot.duca_stock_disponible <= 0:
                    continue
                lot._duca_programar_alerta(company, today)

    def _duca_alerta_responsables(self, company):
        users = self.env['res.users']
        if company.duca_responsable_compras_id:
            users |= company.duca_responsable_compras_id
        if company.duca_responsable_bodega_id:
            users |= company.duca_responsable_bodega_id
        if not users:
            users = self.env.ref('base.user_root')
        return users

    def _duca_programar_alerta(self, company, today):
        self.ensure_one()
        dias = (self.duca_fecha_vencimiento - today).days
        dias_critica = company.duca_dias_alerta_critica or 7
        todo_type = self.env.ref('mail.mail_activity_data_todo')
        responsables = self._duca_alerta_responsables(company)

        if dias < 0:
            marca = 'VENCIDO'
            summary = _('Lote DUCA VENCIDO')
            note = _(
                'El lote DUCA %(duca)s del producto %(prod)s venció el '
                '%(fecha)s y aún tiene stock disponible (%(stock)s). No puede '
                'usarse sin autorización de gerencia. Gestione su '
                'nacionalización, reexportación o destrucción.',
                duca=self.duca_number or self.name,
                prod=self.product_id.display_name,
                fecha=self.duca_fecha_vencimiento,
                stock=self.duca_stock_disponible,
            )
        elif dias <= dias_critica:
            marca = 'CRITICO'
            summary = _('Lote DUCA crítico: vence en %d días') % dias
            note = _(
                'El lote DUCA %(duca)s del producto %(prod)s vence el '
                '%(fecha)s (%(dias)s días). Stock disponible: %(stock)s.',
                duca=self.duca_number or self.name,
                prod=self.product_id.display_name,
                fecha=self.duca_fecha_vencimiento,
                dias=dias,
                stock=self.duca_stock_disponible,
            )
        else:
            marca = 'PREVIO'
            summary = _('Lote DUCA por vencer: %d días') % dias
            note = _(
                'El lote DUCA %(duca)s del producto %(prod)s vence el '
                '%(fecha)s (%(dias)s días). Stock disponible: %(stock)s.',
                duca=self.duca_number or self.name,
                prod=self.product_id.display_name,
                fecha=self.duca_fecha_vencimiento,
                dias=dias,
                stock=self.duca_stock_disponible,
            )

        for user in responsables:
            existente = self.env['mail.activity'].search([
                ('res_model', '=', 'stock.lot'),
                ('res_id', '=', self.id),
                ('activity_type_id', '=', todo_type.id),
                ('user_id', '=', user.id),
                ('summary', 'ilike', 'DUCA'),
            ], limit=1)
            if existente:
                continue
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=summary,
                note=note,
                date_deadline=self.duca_fecha_vencimiento,
                user_id=user.id,
            )

        if marca == 'CRITICO':
            self._duca_enviar_correo_critico(company, responsables, dias)

    def _duca_enviar_correo_critico(self, company, responsables, dias):
        self.ensure_one()
        emails = [u.email for u in responsables if u.email]
        if not emails:
            return
        subject = _('[ZOLI] Lote DUCA crítico %(duca)s vence en %(dias)s días',
                    duca=self.duca_number or self.name, dias=dias)
        body = _(
            '<p>El lote DUCA <strong>%(duca)s</strong> del producto '
            '<strong>%(prod)s</strong> vence el <strong>%(fecha)s</strong> '
            '(%(dias)s días).</p>'
            '<p>Stock disponible: <strong>%(stock)s</strong>.</p>'
            '<p>Empresa: %(empresa)s</p>'
            '<p>Gestione la nacionalización, reexportación o destrucción antes '
            'del vencimiento para evitar el bloqueo de uso del lote.</p>',
            duca=self.duca_number or self.name,
            prod=self.product_id.display_name,
            fecha=self.duca_fecha_vencimiento,
            dias=dias,
            stock=self.duca_stock_disponible,
            empresa=company.name,
        )
        self.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': body,
            'email_to': ','.join(emails),
            'auto_delete': True,
        }).send()
