# -*- coding: utf-8 -*-

import logging

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError, ValidationError
from markupsafe import Markup
import re
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

FISCAL_PREFIX_BY_TYPE = {
    'invoice': 'FAC/%(range_year)s/',
    'credit_note': 'NC/%(range_year)s/',
    'debit_note': 'ND/%(range_year)s/',
    'receipt': 'REC/%(range_year)s/',
    'retention': 'RET/%(range_year)s/',
    'other': 'SEQ/%(range_year)s/',
}

FISCAL_CODE_BY_TYPE = {
    'invoice': 'fiscal.invoice',
    'credit_note': 'fiscal.credit.note',
    'debit_note': 'fiscal.debit.note',
    'receipt': 'fiscal.receipt',
    'retention': 'fiscal.retention',
    'other': 'fiscal.other',
}

FISCAL_NAME_BY_TYPE = {
    'invoice': 'Secuencia Fiscal Facturas',
    'credit_note': 'Secuencia Fiscal Notas de Crédito',
    'debit_note': 'Secuencia Fiscal Notas de Débito',
    'receipt': 'Secuencia Fiscal Recibos',
    'retention': 'Secuencia Fiscal Retenciones',
    'other': 'Secuencia Fiscal',
}


def _fiscal_type_defaults(fiscal_type: str) -> dict:
    """Prefijo, código técnico y nombre sugerido por tipo fiscal."""
    return {
        'prefix': FISCAL_PREFIX_BY_TYPE.get(
            fiscal_type, 'FAC/%(range_year)s/',
        ),
        'code': FISCAL_CODE_BY_TYPE.get(
            fiscal_type, 'fiscal.other',
        ),
        'name': FISCAL_NAME_BY_TYPE.get(
            fiscal_type, 'Secuencia Fiscal',
        ),
    }


class IrSequence(models.Model):
    _name = 'ir.sequence'
    _inherit = ['ir.sequence', 'mail.thread', 'mail.activity.mixin']

    # Campos para control fiscal
    is_fiscal = fields.Boolean(string='Es Secuencia Fiscal', default=False)
    fiscal_type = fields.Selection([
        ('invoice', 'Factura'),
        ('credit_note', 'Nota de Crédito'),
        ('debit_note', 'Nota de Débito'),
        ('receipt', 'Recibo'),
        ('retention', 'Retención'),
        ('other', 'Otro')
    ], string='Tipo Fiscal', default='invoice')

    # Valores por defecto al crear nuevos rangos CAI (detalle)
    default_dias_alerta = fields.Integer(
        string='Default días de alerta (nuevos rangos)',
        default=5,
        help='Valor inicial para el campo "Alertar días antes del vencimiento" '
             'en cada subsecuencia CAI nueva.',
    )
    default_numeros_alerta = fields.Integer(
        string='Default correlativos de alerta (nuevos rangos)',
        default=10,
        help='Valor inicial para el campo "Alertar correlativos restantes" '
             'en cada subsecuencia CAI nueva.',
    )

    @api.model
    def _init_normalize_fiscal_codes(self):
        """Normaliza code/name con espacios heredados de XML multilínea."""
        sequences = self.search([('is_fiscal', '=', True)])
        fixed = 0
        for seq in sequences:
            clean_code = (seq.code or '').strip()
            clean_name = (seq.name or '').strip()
            if seq.code != clean_code or seq.name != clean_name:
                seq.write({'code': clean_code, 'name': clean_name})
                fixed += 1
                _logger.info(
                    'Secuencia fiscal id=%s: code normalizado a %r',
                    seq.id, clean_code,
                )
        if fixed:
            _logger.info(
                'Normalización secuencias fiscales: %d registro(s) corregido(s).',
                fixed,
            )
    
    # Campos de validación fiscal
    fiscal_sequence_validated = fields.Boolean(string='Secuencia Fiscal Validada', default=False)
    fiscal_validation_date = fields.Datetime(string='Fecha de Validación Fiscal', readonly=True)
    fiscal_validation_error = fields.Text(string='Error de Validación Fiscal', readonly=True)
    
    # Control de rangos
    fiscal_range_start = fields.Integer(string='Inicio de Rango Fiscal')
    fiscal_range_end = fields.Integer(string='Fin de Rango Fiscal')
    current_fiscal_number = fields.Integer(string='Número Fiscal Actual', compute='_compute_current_fiscal_number', store=True)
    
    # Alertas y validaciones
    alert_threshold = fields.Integer(string='Umbral de Alerta (%)', default=80, 
                                   help='Porcentaje del rango usado para generar alertas')
    warning_threshold = fields.Integer(string='Umbral de Advertencia (%)', default=90,
                                     help='Porcentaje del rango usado para generar advertencias')
    auto_alert = fields.Boolean(string='Alertas Automáticas', default=True)
    
    # Control de uso
    fiscal_usage_count = fields.Integer(string='Cantidad Usada', compute='_compute_fiscal_usage', store=True)
    fiscal_usage_percentage = fields.Float(string='Porcentaje Usado (%)', compute='_compute_fiscal_usage', store=True)
    last_used_date = fields.Date(string='Última Fecha de Uso', compute='_compute_last_used_date', store=True)
    
    # Validaciones SAR
    requires_cai = fields.Boolean(string='Requiere CAI', default=True)
    cai_validation = fields.Boolean(string='Validar CAI', default=True)
    rtn_validation = fields.Boolean(string='Validar RTN', default=True)
    
    # Campos para reportes
    fiscal_status = fields.Selection([
        ('active', 'Activo'),
        ('warning', 'Advertencia'),
        ('critical', 'Crítico'),
        ('expired', 'Expirado')
    ], string='Estado Fiscal', compute='_compute_fiscal_status', store=True)

    rango_cai_count = fields.Integer(
        string='Rangos CAI',
        compute='_compute_rango_cai_stats',
        store=True,
    )
    active_cai_name = fields.Char(
        string='CAI vigente',
        compute='_compute_rango_cai_stats',
        store=True,
    )
    active_cai_disponibles = fields.Integer(
        string='Disponibles',
        compute='_compute_rango_cai_stats',
        store=True,
    )
    active_cai_consumidos = fields.Integer(
        string='Consumidos',
        compute='_compute_rango_cai_stats',
        store=True,
    )
    active_cai_total = fields.Integer(
        string='Total rango',
        compute='_compute_rango_cai_stats',
        store=True,
    )
    active_cai_uso_label = fields.Char(
        string='Consumo',
        compute='_compute_rango_cai_stats',
        store=True,
    )
    active_cai_vence = fields.Date(
        string='Vence',
        compute='_compute_rango_cai_stats',
        store=True,
    )
    active_cai_vence_label = fields.Char(
        string='Vencimiento',
        compute='_compute_rango_cai_stats',
        store=True,
    )
    fiscal_list_estado = fields.Selection([
        ('ok', 'Activo'),
        ('warning', 'Advertencia'),
        ('expired_date', 'Vencida (fecha)'),
        ('expired_qty', 'Agotada'),
        ('sin_rango', 'Sin rango'),
    ], string='Estado CAI', compute='_compute_rango_cai_stats', store=True)
    fiscal_list_vencida = fields.Boolean(
        string='Vencida',
        compute='_compute_rango_cai_stats',
        store=True,
    )
    fiscal_list_alerta = fields.Boolean(
        string='En alerta',
        compute='_compute_rango_cai_stats',
        store=True,
    )
    journal_count = fields.Integer(
        string='Diarios vinculados',
        compute='_compute_journal_count',
    )
    journal_fiscal_invoice_ids = fields.One2many(
        'account.journal',
        'fiscal_sequence_id',
        string='Diarios — documentos',
    )
    journal_fiscal_refund_ids = fields.One2many(
        'account.journal',
        'refund_fiscal_sequence_id',
        string='Diarios — notas de crédito',
    )

    @api.depends('code', 'name')
    def _compute_journal_count(self) -> None:
        Journal = self.env['account.journal']
        for seq in self:
            if not seq.id:
                seq.journal_count = 0
                continue
            seq.journal_count = Journal.search_count([
                '|',
                ('fiscal_sequence_id', '=', seq.id),
                ('refund_fiscal_sequence_id', '=', seq.id),
            ])

    @api.depends(
        'date_range_ids',
        'date_range_ids.cai',
        'date_range_ids.cai_validated',
        'date_range_ids.date_from',
        'date_range_ids.date_to',
        'date_range_ids.number_next',
        'date_range_ids.number_next_actual',
        'date_range_ids.rangoInicial',
        'date_range_ids.rangoFinal',
        'date_range_ids.dias_alerta',
        'date_range_ids.numeros_alerta',
        'default_dias_alerta',
        'default_numeros_alerta',
    )
    def _compute_rango_cai_stats(self) -> None:
        today = fields.Date.today()
        for seq in self:
            seq.rango_cai_count = len(seq.date_range_ids)
            seq.active_cai_consumidos = 0
            seq.active_cai_total = 0
            seq.active_cai_uso_label = '-'
            seq.active_cai_vence = False
            seq.active_cai_vence_label = _('Sin rango')
            seq.fiscal_list_estado = 'sin_rango'
            seq.fiscal_list_vencida = False
            seq.fiscal_list_alerta = False

            current = seq._fiscal_active_date_ranges_on(today)
            if not current:
                seq.active_cai_name = _('Sin rango activo')
                seq.active_cai_disponibles = 0
                continue

            r = current[0]
            seq.active_cai_name = r.cai or _('Sin CAI')

            total = 0
            usados = 0
            next_number = r.number_next_actual or r.number_next or 0
            if r.rangoInicial and r.rangoFinal:
                total = max(0, r.rangoFinal - r.rangoInicial + 1)
                usados = max(0, next_number - r.rangoInicial)
            seq.active_cai_total = total
            seq.active_cai_consumidos = usados
            seq.active_cai_uso_label = (
                f'{usados}/{total}' if total else '-'
            )
            seq.active_cai_disponibles = max(
                0, r.rangoFinal - next_number + 1,
            ) if r.rangoFinal and next_number else 0

            seq.active_cai_vence = r.date_to
            dias = (r.date_to - today).days if r.date_to else 0
            if r.date_to:
                if dias < 0:
                    seq.active_cai_vence_label = _(
                        'Venció el %s', r.date_to,
                    )
                elif dias == 0:
                    seq.active_cai_vence_label = _(
                        'Vence hoy (%s)', r.date_to,
                    )
                else:
                    seq.active_cai_vence_label = _(
                        '%(days)s días · %(date)s',
                        days=dias,
                        date=r.date_to,
                    )

            dias_alerta = (
                r.dias_alerta or seq.default_dias_alerta or 5
            )
            numeros_alerta = (
                r.numeros_alerta or seq.default_numeros_alerta or 10
            )
            vencido_fecha = bool(r.date_to and today > r.date_to)
            agotado = seq.active_cai_disponibles <= 0 and total > 0
            vencido_qty = bool(
                r.rangoFinal and next_number
                and next_number > r.rangoFinal
            )

            seq.fiscal_list_vencida = vencido_fecha or agotado or vencido_qty
            correlativo_alerta = (
                numeros_alerta > 0
                and total > 0
                and seq.active_cai_disponibles <= numeros_alerta
                and seq.active_cai_disponibles < total
            )
            seq.fiscal_list_alerta = (
                not seq.fiscal_list_vencida
                and (
                    (r.date_to and dias <= dias_alerta)
                    or correlativo_alerta
                )
            )

            if vencido_fecha:
                seq.fiscal_list_estado = 'expired_date'
            elif agotado or vencido_qty:
                seq.fiscal_list_estado = 'expired_qty'
            elif seq.fiscal_list_alerta:
                seq.fiscal_list_estado = 'warning'
            else:
                seq.fiscal_list_estado = 'ok'

    def _fiscal_usable_date_ranges(self, ranges=None, *, require_validated=True):
        """Rangos CAI con datos mínimos; opcionalmente solo validados/activos."""
        self.ensure_one()
        ranges = ranges or self.date_range_ids
        return ranges.filtered(
            lambda r: r.cai and r.rangoInicial and r.rangoFinal
            and (not require_validated or r.cai_validated)
        )

    def _fiscal_active_date_ranges_on(self, ref_date=None):
        """Rangos CAI activos (validados) cuya vigencia incluye ref_date."""
        self.ensure_one()
        ref_date = ref_date or fields.Date.today()
        return self._fiscal_usable_date_ranges().filtered(
            lambda r: r.date_from and r.date_to
            and r.date_from <= ref_date <= r.date_to
        )

    def _fiscal_date_range_for_numbering(self, sequence_date=None):
        """Rango CAI validado a usar al generar el siguiente correlativo."""
        self.ensure_one()
        dt = sequence_date or self._context.get(
            'ir_sequence_date', fields.Date.today(),
        )
        if isinstance(dt, str):
            dt = fields.Date.from_string(dt)
        ranges = self._fiscal_active_date_ranges_on(dt)
        if not ranges:
            return self.env['ir.sequence.date_range']
        if len(ranges) > 1:
            return ranges.sorted('date_from', reverse=True)[0]
        return ranges[0]

    @api.model
    def _get_current_sequence(self, sequence_date=None):
        """Solo rangos CAI activos (cai_validated) para secuencias fiscales."""
        if len(self) == 1 and self.is_fiscal and self.use_date_range:
            seq_date = self._fiscal_date_range_for_numbering(sequence_date)
            if not seq_date:
                ref = sequence_date or fields.Date.today()
                raise UserError(_(
                    'No hay un rango CAI vigente y activo para la secuencia '
                    'fiscal "%(seq)s" en la fecha %(date)s.\n\n'
                    'Active un rango CAI que cubra esa fecha o registre uno '
                    'nuevo antes de numerar documentos.',
                    seq=self.display_name,
                    date=ref,
                ))
            return seq_date
        return super()._get_current_sequence(sequence_date=sequence_date)

    def _next(self, sequence_date=None):
        """Numeración fiscal: ignora rangos CAI desactivados."""
        if self.is_fiscal and self.use_date_range:
            self.ensure_one()
            seq_date = self._fiscal_date_range_for_numbering(sequence_date)
            if not seq_date:
                dt = sequence_date or self._context.get(
                    'ir_sequence_date', fields.Date.today(),
                )
                if isinstance(dt, str):
                    dt = fields.Date.from_string(dt)
                raise UserError(_(
                    'No hay un rango CAI vigente y activo para la secuencia '
                    'fiscal "%(seq)s" en la fecha %(date)s.\n\n'
                    'Active un rango CAI que cubra esa fecha o registre uno '
                    'nuevo antes de numerar documentos.',
                    seq=self.display_name,
                    date=dt,
                ))
            return seq_date.with_context(
                ir_sequence_date_range=fields.Date.to_string(seq_date.date_from),
            )._next()
        return super()._next(sequence_date=sequence_date)
    
    @api.depends('fiscal_range_start', 'fiscal_range_end', 'number_next_actual')
    def _compute_current_fiscal_number(self):
        """Calcular el número fiscal actual"""
        for sequence in self:
            if sequence.fiscal_range_start and sequence.fiscal_range_end:
                sequence.current_fiscal_number = sequence.number_next_actual
            else:
                sequence.current_fiscal_number = 0
    
    @api.depends('fiscal_range_start', 'fiscal_range_end', 'number_next_actual')
    def _compute_fiscal_usage(self):
        """Calcular el uso de la secuencia fiscal"""
        for sequence in self:
            if sequence.fiscal_range_start and sequence.fiscal_range_end:
                total_range = sequence.fiscal_range_end - sequence.fiscal_range_start + 1
                used_range = sequence.number_next_actual - sequence.fiscal_range_start
                sequence.fiscal_usage_count = max(0, used_range)
                sequence.fiscal_usage_percentage = (used_range / total_range * 100) if total_range > 0 else 0
            else:
                sequence.fiscal_usage_count = 0
                sequence.fiscal_usage_percentage = 0
    
    @api.depends('number_next_actual')
    def _compute_last_used_date(self):
        """Calcular la última fecha de uso"""
        for sequence in self:
            # Buscar el último uso en las facturas
            last_invoice = self.env['account.move'].search([
                ('name', 'like', f'%{sequence.prefix}%'),
                ('state', 'in', ['posted', 'cancel'])
            ], order='date desc', limit=1)
            
            sequence.last_used_date = last_invoice.date if last_invoice else False
    
    @api.depends('fiscal_usage_percentage', 'fiscal_range_end', 'number_next_actual')
    def _compute_fiscal_status(self):
        """Calcular el estado fiscal de la secuencia"""
        for sequence in self:
            if not sequence.is_fiscal:
                sequence.fiscal_status = 'active'
                continue
                
            if sequence.fiscal_range_end and sequence.number_next_actual > sequence.fiscal_range_end:
                sequence.fiscal_status = 'expired'
            elif sequence.fiscal_usage_percentage >= sequence.warning_threshold:
                sequence.fiscal_status = 'critical'
            elif sequence.fiscal_usage_percentage >= sequence.alert_threshold:
                sequence.fiscal_status = 'warning'
            else:
                sequence.fiscal_status = 'active'
    
    @api.model
    def _is_fiscal_form_context(self) -> bool:
        ctx = self.env.context
        return bool(ctx.get('fiscal_sequence_form') or ctx.get('default_is_fiscal'))

    @api.model
    def _apply_fiscal_form_defaults(self, vals: dict) -> None:
        vals.setdefault('is_fiscal', True)
        vals.setdefault('use_date_range', True)
        vals.setdefault('implementation', 'no_gap')
        vals.setdefault('padding', 8)
        vals.setdefault('default_dias_alerta', 5)
        vals.setdefault('default_numeros_alerta', 10)
        fiscal_type = vals.get('fiscal_type') or 'invoice'
        vals.setdefault('fiscal_type', fiscal_type)
        suggested = _fiscal_type_defaults(fiscal_type)
        if not vals.get('prefix'):
            vals['prefix'] = suggested['prefix']
        if not vals.get('code'):
            vals['code'] = suggested['code']
        if not vals.get('name'):
            vals['name'] = suggested['name']

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self._is_fiscal_form_context():
            self._apply_fiscal_form_defaults(res)
        return res

    @api.onchange('is_fiscal')
    def _onchange_is_fiscal(self):
        if self.is_fiscal:
            self.use_date_range = True
            self.implementation = 'no_gap'
            if not self.padding:
                self.padding = 8
            if self.fiscal_type:
                self._apply_fiscal_type_suggestions()

    def _apply_fiscal_type_suggestions(self) -> None:
        """Sugiere código, nombre y prefijo según tipo fiscal."""
        if not self.fiscal_type:
            return
        suggested = _fiscal_type_defaults(self.fiscal_type)
        known_codes = set(FISCAL_CODE_BY_TYPE.values())
        known_names = set(FISCAL_NAME_BY_TYPE.values())
        known_prefixes = set(FISCAL_PREFIX_BY_TYPE.values())

        if not self.code or self.code in known_codes:
            self.code = suggested['code']
        if not self.name or self.name in known_names:
            self.name = suggested['name']
        if not self.prefix or self.prefix in known_prefixes:
            self.prefix = suggested['prefix']

    @api.onchange('fiscal_type')
    def _onchange_fiscal_type(self):
        if not self.fiscal_type:
            return
        if self.is_fiscal or self._is_fiscal_form_context():
            self.is_fiscal = True
            self.use_date_range = True
            self.implementation = 'no_gap'
            self._apply_fiscal_type_suggestions()

    def _create_date_range_seq(self, date):
        """Bloquea la auto-creación de rangos vacíos en secuencias fiscales SAR.

        Odoo estándar crea ``ir.sequence.date_range`` sin CAI cuando no hay
        rango vigente; eso dispara el constraint fiscal y mensajes confusos.
        """
        if self.is_fiscal:
            raise UserError(_(
                'No hay un rango CAI vigente para la secuencia fiscal '
                '"%(seq)s".\n\n'
                'Registre un rango CAI (fechas, correlativos y código de '
                'autorización) antes de numerar documentos fiscales.',
                seq=self.display_name,
            ))
        return super()._create_date_range_seq(date)

    def action_open_preregistro_cai(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Preregistro CAI'),
            'res_model': 'kc_fiscal_hn.wizard.preregistro_cai',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sequence_id': self.id,
                'from_fiscal_sequence_form': True,
                'dialog_size': 'large',
            },
        }

    def action_view_journals(self):
        """Abre los diarios que usan esta secuencia fiscal."""
        self.ensure_one()
        journals = self.env['account.journal'].search([
            '|',
            ('fiscal_sequence_id', '=', self.id),
            ('refund_fiscal_sequence_id', '=', self.id),
        ])
        action = self.env['ir.actions.act_window']._for_xml_id(
            'account.action_account_journal_form',
        )
        action['name'] = _('Diarios con secuencia %s', self.name)
        if len(journals) == 1:
            action['views'] = [(False, 'form')]
            action['view_mode'] = 'form'
            action['res_id'] = journals.id
        else:
            action['domain'] = [('id', 'in', journals.ids)]
        return action

    @api.constrains('default_dias_alerta', 'default_numeros_alerta')
    def _check_default_alert_thresholds(self):
        for sequence in self:
            if sequence.default_dias_alerta is not None and sequence.default_dias_alerta < 0:
                raise ValidationError(_(
                    'Los días de alerta por defecto no pueden ser negativos.'
                ))
            if sequence.default_numeros_alerta is not None and sequence.default_numeros_alerta < 0:
                raise ValidationError(_(
                    'Los correlativos de alerta por defecto no pueden ser negativos.'
                ))

    def get_date_deadline_alert(self, document_date=None):
        """
        Evalúa alerta por fecha límite del rango CAI vigente (detalle).
        """
        self.ensure_one()
        if not self.is_fiscal or not self.use_date_range:
            return None

        document_date = document_date or fields.Date.context_today(self)
        status = self.validate_sequence_continuity(document_date)
        if not status.get('valid'):
            return None

        current_range = status.get('current_range')
        if not current_range:
            return None
        return current_range.get_date_deadline_alert(document_date)

    def get_numbers_range_alert(self, document_date=None):
        """
        Evalúa alerta por correlativos restantes del rango CAI vigente (detalle).
        """
        self.ensure_one()
        if not self.is_fiscal or not self.use_date_range:
            return None

        document_date = document_date or fields.Date.context_today(self)
        status = self.validate_sequence_continuity(document_date)
        if not status.get('valid'):
            return None

        current_range = status.get('current_range')
        if not current_range:
            return None
        return current_range.get_numbers_range_alert(document_date)

    def get_fiscal_post_alerts(self, document_date=None):
        """Lista de alertas al confirmar: primero fecha, luego números."""
        self.ensure_one()
        alerts = []
        date_alert = self.get_date_deadline_alert(document_date)
        if date_alert:
            alerts.append(date_alert)
        numbers_alert = self.get_numbers_range_alert(document_date)
        if numbers_alert:
            alerts.append(numbers_alert)
        return alerts

    def format_sequence_number(self, number, sequence_date=None, date_range=None):
        """
        Formatea un número con prefijo/sufijo de la secuencia,
        igual que next_by_id() pero sin consumir el correlativo.
        """
        self.ensure_one()
        ctx = dict(self.env.context)
        if sequence_date:
            if isinstance(sequence_date, str):
                ctx['ir_sequence_date'] = sequence_date
            else:
                ctx['ir_sequence_date'] = fields.Date.to_string(sequence_date)
        if date_range:
            # Odoo 19: ir_sequence_date_range debe ser fecha, no ID del rango
            ctx['ir_sequence_date_range'] = fields.Date.to_string(date_range.date_from)
        sequence = self.with_context(ctx)
        return sequence.get_next_char(int(number))

    @api.constrains('fiscal_range_start', 'fiscal_range_end')
    def _check_fiscal_range(self):
        """Validar que el rango fiscal sea válido"""
        for sequence in self:
            if sequence.fiscal_range_start and sequence.fiscal_range_end:
                if sequence.fiscal_range_start >= sequence.fiscal_range_end:
                    raise ValidationError(_('El inicio del rango fiscal debe ser menor al final'))
                
                if sequence.fiscal_range_start < 1:
                    raise ValidationError(_('El inicio del rango fiscal debe ser mayor a 0'))
    
    @api.constrains('alert_threshold', 'warning_threshold')
    def _check_thresholds(self):
        """Validar que los umbrales sean válidos"""
        for sequence in self:
            if sequence.alert_threshold and sequence.warning_threshold:
                if sequence.alert_threshold >= sequence.warning_threshold:
                    raise ValidationError(_('El umbral de alerta debe ser menor al umbral de advertencia'))
                
                if sequence.alert_threshold < 0 or sequence.alert_threshold > 100:
                    raise ValidationError(_('El umbral de alerta debe estar entre 0 y 100'))
                
                if sequence.warning_threshold < 0 or sequence.warning_threshold > 100:
                    raise ValidationError(_('El umbral de advertencia debe estar entre 0 y 100'))
    
    def action_check_fiscal_sequences(self):
        """Verificar el estado de todas las secuencias fiscales"""
        self.ensure_one()
        
        sequences = self.search([('is_fiscal', '=', True)])
        alerts = []
        
        for sequence in sequences:
            if sequence.fiscal_status == 'critical':
                alerts.append({
                    'sequence': sequence,
                    'type': 'critical',
                    'message': f'La secuencia {sequence.name} está en estado crítico ({sequence.fiscal_usage_percentage:.1f}% usado)'
                })
            elif sequence.fiscal_status == 'warning':
                alerts.append({
                    'sequence': sequence,
                    'type': 'warning',
                    'message': f'La secuencia {sequence.name} está en advertencia ({sequence.fiscal_usage_percentage:.1f}% usado)'
                })
            elif sequence.fiscal_status == 'expired':
                alerts.append({
                    'sequence': sequence,
                    'type': 'expired',
                    'message': f'La secuencia {sequence.name} ha expirado'
                })
        
        if alerts:
            return self._show_sequence_alerts(alerts)
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Verificación Completada'),
                    'message': _('Todas las secuencias fiscales están en buen estado'),
                    'type': 'success',
                }
            }
    
    def _show_sequence_alerts(self, alerts):
        """Mostrar alertas de secuencias"""
        return {
            'name': _('Alertas de Secuencias Fiscales'),
            'type': 'ir.actions.act_window',
            'res_model': 'kc_fiscal_hn.wizard.sequence_alerts',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_alerts': str(alerts),
                'default_alert_count': len(alerts)
            }
        }
    
    def action_reset_fiscal_sequence(self):
        """Reiniciar secuencia fiscal"""
        self.ensure_one()
        
        if not self.is_fiscal:
            raise ValidationError(_('Esta secuencia no es fiscal'))
        
        return {
            'name': _('Reiniciar Secuencia Fiscal'),
            'type': 'ir.actions.act_window',
            'res_model': 'kc_fiscal_hn.wizard.reset_sequence',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sequence_id': self.id,
                'default_current_number': self.number_next_actual,
                'default_fiscal_range_start': self.fiscal_range_start,
                'default_fiscal_range_end': self.fiscal_range_end
            }
        }
    
    def action_view_fiscal_usage(self):
        """Ver el uso de la secuencia fiscal"""
        self.ensure_one()
        
        if not self.is_fiscal:
            raise ValidationError(_('Esta secuencia no es fiscal'))
        
        # Buscar documentos que usan esta secuencia
        domain = [
            ('name', 'like', f'%{self.prefix}%'),
            ('state', 'in', ['posted', 'cancel'])
        ]
        
        return {
            'name': _('Uso de Secuencia Fiscal'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'default_name': self.prefix,
                'search_default_fiscal_sequence': True
            }
        }
    
    def get_next_fiscal_number(self):
        """Obtener el próximo número fiscal con validaciones"""
        self.ensure_one()
        
        if not self.is_fiscal:
            return self._next()
        
        # Validar que no haya expirado
        if self.fiscal_status == 'expired':
            raise ValidationError(_(f'La secuencia fiscal {self.name} ha expirado. Contacte al administrador.'))
        
        # Validar que esté dentro del rango
        if self.fiscal_range_end and self.number_next_actual > self.fiscal_range_end:
            raise ValidationError(_(f'La secuencia fiscal {self.name} ha excedido su rango máximo.'))
        
        # Generar alertas si es necesario
        if self.auto_alert and self.fiscal_status in ['warning', 'critical']:
            self._generate_sequence_alert()
        
        return self._next()
    
    def _generate_sequence_alert(self):
        """Generar alerta automática para la secuencia"""
        self.ensure_one()
        
        # Crear alerta en el sistema
        self.env['kc_fiscal_hn.sequence.alert'].create({
            'sequence_id': self.id,
            'alert_type': self.fiscal_status,
            'message': f'La secuencia {self.name} está en estado {self.fiscal_status} ({self.fiscal_usage_percentage:.1f}% usado)',
            'usage_percentage': self.fiscal_usage_percentage,
            'current_number': self.number_next_actual,
            'range_start': self.fiscal_range_start,
            'range_end': self.fiscal_range_end
        })
    
    # Caracteres que rompen la regex de `sequence.mixin._compute_split_sequence`
    # de Odoo (el comodín `.` no admite saltos de línea), provocando un
    # AttributeError al confirmar facturas con esta secuencia.
    _AFFIX_INVALID_CHARS_RE = re.compile(r'[\r\n\t\v\f\x00-\x1f\x85\u2028\u2029]')

    @api.model
    def _clean_affix_vals(self, vals):
        """Elimina saltos de línea/control del prefijo y sufijo de la secuencia."""
        for field in ('prefix', 'suffix'):
            value = vals.get(field)
            if value and isinstance(value, str):
                cleaned = self._AFFIX_INVALID_CHARS_RE.sub('', value).strip()
                if cleaned != value:
                    _logger.warning(
                        "Secuencia fiscal: %s contenía caracteres inválidos "
                        "(saltos de línea/control) y fue saneado.", field,
                    )
                    vals[field] = cleaned

    @api.model_create_multi
    def create(self, vals_list):
        """Crear secuencias con validaciones fiscales"""
        if self._is_fiscal_form_context():
            for vals in vals_list:
                self._apply_fiscal_form_defaults(vals)
        for vals in vals_list:
            self._clean_affix_vals(vals)
        sequences = super().create(vals_list)
        
        for sequence in sequences:
            if sequence.is_fiscal:
                sequence._validate_fiscal_sequence()
        
        return sequences
    
    # Campos cuyo cambio se registra en el chatter de la secuencia fiscal
    _SEQUENCE_CHATTER_FIELDS = {
        'name': 'Nombre',
        'prefix': 'Prefijo',
        'suffix': 'Sufijo',
        'padding': 'Tamaño correlativo',
        'number_increment': 'Incremento',
        'active': 'Activa',
        'fiscal_type': 'Tipo fiscal',
        'is_fiscal': 'Es secuencia fiscal',
        'default_dias_alerta': 'Default alerta (días)',
        'default_numeros_alerta': 'Default alerta (correlativos)',
        'fiscal_sequence_validated': 'Validada',
    }

    def _format_chatter_value(self, value):
        if value in (False, None):
            return '—'
        if value is True:
            return _('Sí')
        return value

    def write(self, vals):
        """Escribir secuencia con validaciones fiscales y registro en chatter."""
        self._clean_affix_vals(vals)
        tracked = {
            f: lbl for f, lbl in self._SEQUENCE_CHATTER_FIELDS.items()
            if f in vals
        }
        previous = {}
        if tracked:
            previous = {
                seq.id: {f: seq[f] for f in tracked}
                for seq in self
            }

        result = super().write(vals)

        for sequence in self:
            if not sequence.is_fiscal:
                continue
            sequence._validate_fiscal_sequence()
            if not tracked:
                continue
            changes = []
            for field_name, label in tracked.items():
                old = previous.get(sequence.id, {}).get(field_name)
                new = sequence[field_name]
                if old == new:
                    continue
                changes.append(_(
                    '%(label)s: %(old)s → %(new)s',
                    label=label,
                    old=sequence._format_chatter_value(old),
                    new=sequence._format_chatter_value(new),
                ))
            if changes:
                sequence.message_post(
                    body=Markup('%s<br/>%s') % (
                        _('Configuración de la secuencia actualizada:'),
                        Markup('<br/>').join(Markup('%s') % c for c in changes),
                    ),
                )

        return result
    
    def _validate_fiscal_sequence(self):
        """Validar configuración básica de secuencia fiscal"""
        self.ensure_one()
        
        # Validar prefijo (solo una vez)
        if not self.prefix or len(self.prefix.strip()) == 0:
            raise ValidationError(_('Las secuencias fiscales deben tener un prefijo válido'))
    
    def _validate_fiscal_ranges(self):
        """Validar rangos fiscales de la secuencia"""
        self.ensure_one()
        
        # Si usa rangos de fecha, validar que existan rangos de fecha con CAI
        if self.use_date_range:
            # Buscar rangos de fecha que tengan CAI y rangos definidos
            date_ranges = self._fiscal_usable_date_ranges(require_validated=False)
            
            if not date_ranges:
                raise ValidationError(_('Las secuencias fiscales con rangos de fecha deben tener al menos un rango con CAI y rangos definidos'))
            
            # Validar que los rangos de fecha sean válidos
            for date_range in date_ranges:
                if date_range.rangoInicial >= date_range.rangoFinal:
                    raise ValidationError(_('El rango inicial debe ser menor al rango final en el rango de fecha'))
                
                # # Validar que el CAI tenga formato válido
                # if date_range.cai and not re.match(r'^[A-Z0-9]{37}$', date_range.cai):
                #     raise ValidationError(_('El CAI debe tener 37 caracteres alfanuméricos'))
                
                # Validar que las fechas del rango sean válidas (usando date_from y date_to de Odoo)
                if date_range.date_from and date_range.date_to:
                    if date_range.date_from >= date_range.date_to:
                        raise ValidationError(_('La fecha de inicio debe ser menor a la fecha de fin en el rango de fecha'))
        else:
            # Si no usa rangos de fecha, validar los rangos de la secuencia principal
            if not self.fiscal_range_start or not self.fiscal_range_end:
                raise ValidationError(_('Las secuencias fiscales deben tener un rango definido'))
            
            if self.fiscal_range_start >= self.fiscal_range_end:
                raise ValidationError(_('El rango inicial debe ser menor al rango final'))
    
    def _validate_date_range_current(self):
        """Validar que exista un rango de fecha válido para el período actual"""
        self.ensure_one()
        
        if not self.use_date_range:
            return True
        
        # Buscar rango de fecha para hoy
        current_date_range = self._fiscal_active_date_ranges_on(fields.Date.today())
        if not current_date_range:
            # Si no hay rango activo validado, buscar el más reciente aún utilizable
            current_date_range = self._fiscal_usable_date_ranges().filtered(
                lambda r: r.date_to and r.date_to >= fields.Date.today()
            ).sorted('date_to', reverse=True)
        
        if not current_date_range:
            raise ValidationError(_('No hay rangos de fecha válidos para el período actual'))
        
        # Validar que el rango de fecha actual tenga CAI y rangos válidos
        current_range = current_date_range[0]
        if not current_range.cai:
            raise ValidationError(_('El rango de fecha actual no tiene CAI configurado'))
        
        if not current_range.rangoInicial or not current_range.rangoFinal:
            raise ValidationError(_('El rango de fecha actual no tiene rangos inicial y final configurados'))
        
        if current_range.rangoInicial >= current_range.rangoFinal:
            raise ValidationError(_('El rango inicial debe ser menor al rango final en el período actual'))
        
        return True
    
    def _validate_sequence_numbers(self):
        """Validar que el número actual esté dentro del rango fiscal"""
        self.ensure_one()
        
        if not self.use_date_range:
            # Para rangos de secuencia principal
            if self.number_next_actual < self.fiscal_range_start:
                raise ValidationError(_('El número actual está por debajo del rango fiscal'))
            
            if self.fiscal_range_end and self.number_next_actual > self.fiscal_range_end:
                raise ValidationError(_('El número actual está por encima del rango fiscal'))
        
        return True
    
    def _clear_validation_state(self):
        """Limpiar estado de validación"""
        self.write({
            'fiscal_sequence_validated': False,
            'fiscal_validation_date': fields.Datetime.now(),
            'fiscal_validation_error': False
        })
    
    def _set_validation_success(self):
        """Marcar validación como exitosa"""
        self.write({
            'fiscal_sequence_validated': True,
            'fiscal_validation_date': fields.Datetime.now(),
            'fiscal_validation_error': False
        })
    
    def _set_validation_error(self, error_message):
        """Marcar validación como fallida"""
        self.write({
            'fiscal_sequence_validated': False,
            'fiscal_validation_date': fields.Datetime.now(),
            'fiscal_validation_error': error_message
        })
    
    def _return_validation_result(self, success=True, title='', message='', error_message=''):
        """Retornar resultado de validación estandarizado"""
        if success:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': title,
                    'message': message,
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': title,
                    'message': error_message,
                    'type': 'danger',
                }
            }
    
    def validate_fiscal_sequence_complete(self):
        """Validar secuencia fiscal completa"""
        self.ensure_one()
        
        # Limpiar estado anterior
        self._clear_validation_state()
        
        try:
            # Validar configuración básica
            self._validate_fiscal_sequence()
            
            # Validar rangos fiscales
            self._validate_fiscal_ranges()
            
            # Validar que el número actual esté dentro del rango
            self._validate_sequence_numbers()
            
            # Validar que exista un rango de fecha válido para el período actual
            self._validate_date_range_current()
            
            # Si llegamos aquí, la validación fue exitosa
            self._set_validation_success()
            
            return self._return_validation_result(title=_('Validación Exitosa'), message=_('La secuencia fiscal ha sido validada correctamente'))
            
        except Exception as e:
            # Si hay error, guardar el error y devolver mensaje de error
            self._set_validation_error(str(e))
            
            return self._return_validation_result(title=_('Error de Validación'), error_message=str(e))
    
    def validate_fiscal_sequence_simple(self):
        """Validación simple para diagnosticar problemas"""
        self.ensure_one()
        
        # Limpiar estado anterior
        self._clear_validation_state()
        
        try:
            # Verificar si usa rangos de fecha
            if self.use_date_range:
                # Contar rangos de fecha con CAI y rangos
                valid_ranges = self._fiscal_usable_date_ranges(require_validated=False)
                
                if len(valid_ranges) == 0:
                    raise ValidationError(_('No hay rangos de fecha con CAI y rangos definidos'))
                
                # Marcar como válida
                self._set_validation_success()
                
                return self._return_validation_result(title=_('Validación Simple Exitosa'), message=_('La secuencia fiscal ha sido validada correctamente'))
            else:
                raise ValidationError(_('Esta secuencia no usa rangos de fecha'))
                
        except Exception as e:
            self._set_validation_error(str(e))
            
            return self._return_validation_result(title=_('Error de Validación Simple'), error_message=str(e))
    
    def get_fiscal_dashboard_data(self):
        """Obtener datos para el dashboard fiscal"""
        sequences = self.search([('is_fiscal', '=', True)])
        
        total_sequences = len(sequences)
        active_sequences = len(sequences.filtered(lambda s: s.fiscal_status == 'active'))
        warning_sequences = len(sequences.filtered(lambda s: s.fiscal_status == 'warning'))
        critical_sequences = len(sequences.filtered(lambda s: s.fiscal_status == 'critical'))
        expired_sequences = len(sequences.filtered(lambda s: s.fiscal_status == 'expired'))
        
        # Calcular uso total
        total_usage = sum(sequences.mapped('fiscal_usage_count'))
        total_range = sum([(s.fiscal_range_end - s.fiscal_range_start + 1) for s in sequences if s.fiscal_range_start and s.fiscal_range_end])
        overall_usage_percentage = (total_usage / total_range * 100) if total_range > 0 else 0
        
        return {
            'total_sequences': total_sequences,
            'active_sequences': active_sequences,
            'warning_sequences': warning_sequences,
            'critical_sequences': critical_sequences,
            'expired_sequences': expired_sequences,
            'overall_usage_percentage': overall_usage_percentage,
            'sequences': sequences
        }
    
    def validate_fiscal_sequence_date_ranges(self):
        """Validar específicamente secuencias con rangos de fecha"""
        self.ensure_one()
        
        if not self.use_date_range:
            raise ValidationError(_('Esta secuencia no usa rangos de fecha'))
        
        # Limpiar estado anterior
        self._clear_validation_state()
        
        try:
            # Validar que existan rangos de fecha
            if not self.date_range_ids:
                raise ValidationError(_('No hay rangos de fecha configurados'))
            
            # Validar que al menos un rango tenga CAI y rangos válidos
            valid_ranges = self._fiscal_usable_date_ranges(require_validated=False)
            
            if not valid_ranges:
                raise ValidationError(_('No hay rangos de fecha con CAI y rangos definidos'))
            
            # Validar que exista un rango para el período actual o futuro
            today = fields.Date.today()
            current_or_future_ranges = self._fiscal_usable_date_ranges(
                self.date_range_ids.filtered(lambda r: r.date_to and r.date_to >= today),
                require_validated=False,
            )
            
            if not current_or_future_ranges:
                raise ValidationError(_('No hay rangos de fecha válidos para el período actual o futuro'))
            
            # Validar cada rango (usar la función centralizada)
            for date_range in valid_ranges:
                if date_range.rangoInicial >= date_range.rangoFinal:
                    raise ValidationError(_(f'El rango inicial debe ser menor al rango final en el rango de fecha {date_range.date_from} - {date_range.date_to}'))
                
                if date_range.cai and not re.match(r'^[A-Z0-9]{37}$', date_range.cai):
                    raise ValidationError(_(f'El CAI del rango {date_range.date_from} - {date_range.date_to} debe tener 37 caracteres alfanuméricos'))
                
                if date_range.date_from and date_range.date_to:
                    if date_range.date_from >= date_range.date_to:
                        raise ValidationError(_(f'El rango {date_range.date_from} - {date_range.date_to} tiene una fecha de inicio mayor o igual a la fecha de fin'))
            
            # Marcar como válida
            self._set_validation_success()
            
            return self._return_validation_result(title=_('Validación de Rangos de Fecha Exitosa'), message=_('Los rangos de fecha de la secuencia fiscal han sido validados correctamente'))
            
        except Exception as e:
            self._set_validation_error(str(e))
            
            return self._return_validation_result(title=_('Error de Validación de Rangos de Fecha'), error_message=str(e))

    def get_available_future_ranges(self, current_date=None):
        """
        Obtener rangos de fecha futuros disponibles que permitan continuar operaciones
        """
        self.ensure_one()
        
        if not self.use_date_range:
            return self.env['ir.sequence.date_range']
        
        if not current_date:
            current_date = fields.Date.today()
        
        # Buscar rangos futuros que tengan CAI y rangos válidos
        future_ranges = self._fiscal_usable_date_ranges(
            self.date_range_ids.filtered(lambda r:
                r.date_from and r.date_to and r.date_from < r.date_to
                and (
                    r.date_from > current_date
                    or (r.date_from <= current_date <= r.date_to)
                )
            ),
        ).sorted('date_from')
        
        return future_ranges
    
    def has_valid_future_sequences(self, current_date=None):
        """
        Verificar si existen subsecuencias futuras válidas que permitan continuar operaciones
        """
        self.ensure_one()
        
        if not self.use_date_range:
            return True
        
        future_ranges = self.get_available_future_ranges(current_date)
        return len(future_ranges) > 0
    
    def get_next_available_range(self, current_date=None):
        """
        Obtener el siguiente rango de fecha disponible
        """
        self.ensure_one()
        
        if not self.use_date_range:
            return False
        
        if not current_date:
            current_date = fields.Date.today()
        
        # Buscar el siguiente rango válido
        next_range = self._fiscal_usable_date_ranges(
            self.date_range_ids.filtered(lambda r:
                r.date_from and r.date_to and r.date_from < r.date_to
                and r.date_from > current_date
            ),
        ).sorted('date_from')
        
        return next_range[0] if next_range else False
    
    def validate_sequence_continuity(self, current_date=None):
        """
        Validar continuidad de la secuencia fiscal, permitiendo operaciones si hay subsecuencias futuras
        """
        self.ensure_one()
        
        if not self.use_date_range:
            return {'valid': True, 'message': '', 'can_continue': True}
        
        if not current_date:
            current_date = fields.Date.today()
        
        # Obtener rango actual
        current_range = self._fiscal_active_date_ranges_on(current_date)
        
        if not current_range:
            # Buscar rango futuro más cercano
            future_range = self.get_next_available_range(current_date)
            if future_range:
                return {
                    'valid': True, 
                    'message': f'No hay rango para la fecha actual, pero existe rango futuro desde {future_range.date_from}',
                    'can_continue': True,
                    'next_range': future_range
                }
            else:
                return {
                    'valid': False,
                    'message': 'No hay rangos de fecha válidos para la fecha actual ni futuros',
                    'can_continue': False
                }
        
        current_range = current_range[0]
        
        # Validar rango actual
        if not current_range.cai:
            return {
                'valid': False,
                'message': f'El rango de fecha {current_range.date_from} - {current_range.date_to} no tiene CAI configurado',
                'can_continue': False
            }
        
        if not current_range.rangoInicial or not current_range.rangoFinal:
            return {
                'valid': False,
                'message': f'El rango de fecha {current_range.date_from} - {current_range.date_to} no tiene rangos numéricos configurados',
                'can_continue': False
            }
        
        if current_range.rangoInicial >= current_range.rangoFinal:
            return {
                'valid': False,
                'message': f'El rango numérico {current_range.rangoInicial}-{current_range.rangoFinal} no es válido',
                'can_continue': False
            }
        
        # Verificar si el rango actual está próximo a vencer
        warnings = []
        can_continue = True
        
        # Alerta de fecha (configuración por rango CAI / detalle)
        if current_range.date_to and current_range.dias_alerta:
            dias_restantes = (current_range.date_to - current_date).days
            if dias_restantes <= 0:
                warnings.append(f'Fecha límite vencida: {current_range.date_to}')
                can_continue = False
            elif dias_restantes <= current_range.dias_alerta:
                warnings.append(
                    f'Fecha límite próxima: {current_range.date_to} '
                    f'(quedan {dias_restantes} días, alerta en {current_range.dias_alerta})'
                )
        
        # Alerta de números (configuración por rango CAI / detalle)
        if current_range.numeros_alerta and current_range.rangoInicial and current_range.rangoFinal:
            numeros_restantes = current_range.rangoFinal - current_range.number_next_actual + 1
            if numeros_restantes <= 0:
                warnings.append(f'Rango numérico agotado: {current_range.rangoInicial}-{current_range.rangoFinal}')
                can_continue = False
            elif numeros_restantes <= current_range.numeros_alerta:
                warnings.append(
                    f'Rango numérico próximo a agotarse: quedan {numeros_restantes} números '
                    f'(alerta en {current_range.numeros_alerta})'
                )
        
        # Verificar si hay subsecuencias futuras que permitan continuar
        if not can_continue:
            future_ranges = self.get_available_future_ranges(current_date)
            if future_ranges:
                can_continue = True
                warnings.append(f'Existen {len(future_ranges)} rangos futuros disponibles que permiten continuar operaciones')
        
        return {
            'valid': True,
            'message': '; '.join(warnings) if warnings else 'Rango válido',
            'can_continue': can_continue,
            'current_range': current_range,
            'warnings': warnings
        }
    
    def get_fiscal_sequence_status(self, current_date=None):
        """
        Obtener estado completo de la secuencia fiscal para mostrar en el dashboard
        """
        self.ensure_one()
        
        if not current_date:
            current_date = fields.Date.today()
        
        # Validar continuidad
        continuity = self.validate_sequence_continuity(current_date)
        
        # Obtener rangos futuros
        future_ranges = self.get_available_future_ranges(current_date)
        
        # Calcular estadísticas
        total_ranges = len(self.date_range_ids)
        valid_ranges = len(self._fiscal_usable_date_ranges(require_validated=False))
        expired_ranges = len(self.date_range_ids.filtered(lambda r: r.date_to and r.date_to < current_date))
        future_ranges_count = len(future_ranges)
        
        return {
            'sequence_name': self.name,
            'is_fiscal': self.is_fiscal,
            'use_date_range': self.use_date_range,
            'continuity': continuity,
            'total_ranges': total_ranges,
            'valid_ranges': valid_ranges,
            'expired_ranges': expired_ranges,
            'future_ranges': future_ranges_count,
            'can_continue_operations': continuity['can_continue'],
            'status': 'active' if continuity['can_continue'] else 'critical',
            'last_validation': self.fiscal_validation_date,
            'validation_error': self.fiscal_validation_error
        }

    def check_sequence_expiration(self):
        """
        Rangos CAI agotados o con correlativos restantes
        dentro del umbral numeros_alerta (para wizard de alertas).
        """
        self.ensure_one()
        today = fields.Date.context_today(self)
        alerts = []
        for date_range in self.date_range_ids:
            if not date_range.rangoInicial or not date_range.rangoFinal:
                continue
            if date_range.date_to and date_range.date_to < today:
                continue
            remaining = (
                date_range.rangoFinal - date_range.number_next_actual + 1
            )
            threshold = date_range.numeros_alerta or 0
            if threshold <= 0:
                continue
            if remaining > threshold:
                continue
            alerts.append({
                'sequence': self.name,
                'date_range': (
                    f'{date_range.date_from} — {date_range.date_to}'
                ),
                'remaining': remaining,
                'cai': date_range.cai or '',
                'exhausted': remaining <= 0,
            })
        return alerts

    @api.model
    def _cron_activar_siguiente_rango(self) -> None:
        """
        Cron diario: verifica secuencias fiscales
        y activa el siguiente rango CAI cuando:
        - El rango actual se agotó (números usados)
        - El rango actual venció (fecha límite)
        """
        today = fields.Date.today()
        secuencias = self.search([('is_fiscal', '=', True)])
        if secuencias:
            secuencias._recompute_recordset([
                'fiscal_list_vencida',
                'fiscal_list_alerta',
                'fiscal_list_estado',
                'active_cai_uso_label',
                'active_cai_vence',
                'active_cai_vence_label',
                'active_cai_disponibles',
                'active_cai_consumidos',
                'active_cai_name',
            ])

        for seq in secuencias:
            current = seq._fiscal_active_date_ranges_on(today)
            if not current:
                continue

            r = current[0]
            agotado = (
                r.rangoFinal
                and r.number_next_actual > r.rangoFinal
            )
            vencido = r.date_to < today

            if not agotado and not vencido:
                continue

            siguiente = seq._fiscal_usable_date_ranges(
                seq.date_range_ids.filtered(lambda dr: dr.date_from and dr.date_from > r.date_to),
            ).sorted('date_from')

            if not siguiente:
                self.env['kc_fiscal_hn.sequence.alert'].create({
                    'sequence_id': seq.id,
                    'alert_type': 'critical',
                    'message': (
                        f'Secuencia {seq.name}: rango CAI '
                        f'{"agotado" if agotado else "vencido"} '
                        f'sin rango siguiente preregistrado. '
                        f'Registre un nuevo CAI urgentemente.'
                    ),
                    'current_number': r.number_next_actual,
                    'range_start': r.rangoInicial,
                    'range_end': r.rangoFinal,
                })
                continue

            sig = siguiente[0]
            motivo = 'rango agotado' if agotado else 'fecha vencida'

            activacion_vals = {}
            if sig.date_from > today:
                activacion_vals['date_from'] = today
            if activacion_vals:
                sig.sudo().write(activacion_vals)

            if agotado and not vencido and r.date_to >= today:
                r.sudo().write({'date_to': today - timedelta(days=1)})

            self.env['kc_fiscal_hn.sequence.audit'].create({
                'sequence_id': seq.id,
                'action': 'modify',
                'old_number': r.number_next_actual,
                'new_number': sig.rangoInicial,
                'reason': (
                    f'Activación automática por cron: '
                    f'{motivo}. Nuevo rango CAI: '
                    f'{sig.cai} ({sig.rangoInicial}-'
                    f'{sig.rangoFinal})'
                ),
                'user_id': self.env.ref('base.user_root').id,
            })

            self.env['kc_fiscal_hn.sequence.alert'].create({
                'sequence_id': seq.id,
                'alert_type': 'warning',
                'message': (
                    f'Se activó automáticamente el nuevo '
                    f'rango CAI {sig.cai} para {seq.name}. '
                    f'Rango: {sig.rangoInicial}-{sig.rangoFinal}. '
                    f'Vigencia: {sig.date_from} al {sig.date_to}.'
                ),
                'current_number': sig.rangoInicial,
                'range_start': sig.rangoInicial,
                'range_end': sig.rangoFinal,
            })

            _logger.info(
                'Rango CAI activado automáticamente: '
                'secuencia=%s, CAI=%s, rango=%s-%s',
                seq.name, sig.cai,
                sig.rangoInicial, sig.rangoFinal,
            )


class IrSequenceDateRange(models.Model):
    _inherit = 'ir.sequence.date_range'

    cai = fields.Char(string='CAI', help='Clave de Autorización de Impresión')
    rangoInicial = fields.Integer(string='Rango inicial', help='Rango inicial')
    rangoFinal = fields.Integer(string='Rango final', help='Rango final')
    dias_alerta = fields.Integer(
        string='Alertar días antes del vencimiento',
        default=5,
        help='Días antes de la fecha límite (Hasta) de este rango CAI para '
             'mostrar advertencia al confirmar facturas. 0 = desactivado.',
    )
    numeros_alerta = fields.Integer(
        string='Alertar correlativos restantes',
        default=10,
        help='Alerta al confirmar cuando queden esta cantidad de correlativos '
             'o menos en este rango CAI. 0 = desactivado.',
    )
    cai_validated = fields.Boolean(
        string='CAI validado / activo',
        default=False,
        help='Si está desmarcado, el rango CAI queda inactivo y no se usa '
             'para emitir documentos fiscales.',
    )
    cai_validation_date = fields.Datetime(string='Fecha de Validación CAI', readonly=True)
    cai_validation_error = fields.Text(string='Error de Validación CAI', readonly=True)

    disponibles = fields.Integer(
        string='Disponibles',
        compute='_compute_rango_usage',
    )
    uso_porcentaje = fields.Float(
        string='Uso (%)',
        compute='_compute_rango_usage',
    )
    dias_restantes = fields.Integer(
        string='Días restantes',
        compute='_compute_rango_usage',
    )
    es_vigente = fields.Boolean(
        string='Vigente hoy',
        compute='_compute_rango_usage',
    )
    estado_rango = fields.Selection([
        ('future', 'Futuro'),
        ('active', 'Activo'),
        ('warning', 'Advertencia'),
        ('critical', 'Crítico'),
        ('expired', 'Vencido'),
        ('inactive', 'Desactivado'),
    ], string='Estado', compute='_compute_rango_usage')
    can_manage_fiscal_range = fields.Boolean(
        compute='_compute_can_manage_fiscal_range',
    )

    @api.depends_context('uid')
    def _compute_can_manage_fiscal_range(self):
        can_manage = self.env.user.has_group(
            'kc_fiscal_hn_v18.group_fiscal_sequence_manager',
        )
        for record in self:
            record.can_manage_fiscal_range = can_manage

    @api.depends(
        'date_from',
        'date_to',
        'rangoInicial',
        'rangoFinal',
        'number_next',
        'number_next_actual',
        'cai_validated',
        'dias_alerta',
        'numeros_alerta',
        'sequence_id.default_dias_alerta',
        'sequence_id.default_numeros_alerta',
    )
    def _compute_rango_usage(self) -> None:
        today = fields.Date.today()
        for r in self:
            if not r.cai_validated:
                r.es_vigente = False
                r.disponibles = 0
                r.uso_porcentaje = 0.0
                r.dias_restantes = (
                    (r.date_to - today).days if r.date_to else 0
                )
                r.estado_rango = 'inactive'
                continue

            r.es_vigente = bool(
                r.date_from and r.date_to
                and r.date_from <= today <= r.date_to
            )
            next_number = r.number_next_actual or r.number_next or 0
            if r.rangoFinal and r.rangoInicial and next_number:
                total = max(1, r.rangoFinal - r.rangoInicial + 1)
                usados = max(0, next_number - r.rangoInicial)
                r.disponibles = max(0, r.rangoFinal - next_number + 1)
                r.uso_porcentaje = min(100.0, usados / total * 100)
            else:
                r.disponibles = 0
                r.uso_porcentaje = 0.0

            r.dias_restantes = (
                (r.date_to - today).days if r.date_to else 0
            )
            dias_alerta = (
                r.dias_alerta
                or r.sequence_id.default_dias_alerta
                or 5
            )
            numeros_alerta = (
                r.numeros_alerta
                or r.sequence_id.default_numeros_alerta
                or 10
            )

            if r.date_from and today < r.date_from:
                r.estado_rango = 'future'
            elif r.date_to and today > r.date_to:
                r.estado_rango = 'expired'
            elif r.disponibles <= 0:
                r.estado_rango = 'critical'
            elif (
                r.disponibles < total
                and numeros_alerta > 0
                and r.disponibles <= numeros_alerta
            ) or (
                r.dias_restantes <= dias_alerta
                and r.dias_restantes >= 0
                and total > 0
                and r.disponibles < total
            ):
                r.estado_rango = 'warning'
            else:
                r.estado_rango = 'active'

    # Campos cuyo cambio se registra en el chatter de la secuencia
    _CHATTER_FIELDS = {
        'cai': 'CAI',
        'rangoInicial': 'Rango inicial',
        'rangoFinal': 'Rango final',
        'date_from': 'Vigente desde',
        'date_to': 'Fecha límite',
        'dias_alerta': 'Alerta (días)',
        'numeros_alerta': 'Alerta (correlativos)',
        'number_next_actual': 'Siguiente correlativo',
        'number_next': 'Siguiente correlativo',
        'cai_validated': 'CAI activo',
    }

    _FISCAL_MANAGER_EDIT_FIELDS = frozenset({
        'cai', 'rangoInicial', 'rangoFinal', 'date_from', 'date_to',
        'number_next', 'number_next_actual', 'cai_validated',
        'dias_alerta', 'numeros_alerta',
    })

    @api.onchange('rangoInicial')
    def _onchange_rango_inicial_sync_number_next(self):
        for record in self:
            if not record.sequence_id.is_fiscal or not record.rangoInicial:
                continue
            if not record.number_next or record.number_next < record.rangoInicial:
                record.number_next = record.rangoInicial

    def _check_fiscal_range_write_access(self, vals):
        """Solo el Administrador de Numeración Fiscal puede editar rangos SAR."""
        if not vals:
            return
        fiscal_ranges = self.filtered(
            lambda r: r.sequence_id and r.sequence_id.is_fiscal,
        )
        if not fiscal_ranges:
            return
        if set(vals) & self._FISCAL_MANAGER_EDIT_FIELDS:
            if not self.env.user.has_group(
                'kc_fiscal_hn_v18.group_fiscal_sequence_manager',
            ):
                raise AccessError(_(
                    'Solo el Administrador de Numeración Fiscal puede '
                    'modificar rangos CAI.',
                ))

    @api.model_create_multi
    def create(self, vals_list):
        Sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('sequence_id'):
                sequence = Sequence.browse(vals['sequence_id'])
                if sequence.is_fiscal:
                    vals.setdefault(
                        'dias_alerta',
                        sequence.default_dias_alerta if sequence.default_dias_alerta is not None else 5,
                    )
                    vals.setdefault(
                        'numeros_alerta',
                        sequence.default_numeros_alerta if sequence.default_numeros_alerta is not None else 10,
                    )
                    # number_next_actual es calculado; el valor persistente es number_next.
                    if vals.get('rangoInicial') and not vals.get('number_next'):
                        vals['number_next'] = vals['rangoInicial']
                    elif vals.get('number_next_actual') and not vals.get('number_next'):
                        vals['number_next'] = vals['number_next_actual']
        records = super().create(vals_list)
        for record in records:
            sequence = record.sequence_id
            if sequence and sequence.is_fiscal:
                sequence.message_post(body=Markup(
                    _('Nuevo rango CAI registrado: '
                      '<b>%(cai)s</b> (%(ini)s–%(fin)s), '
                      'vigencia %(desde)s al %(hasta)s.')
                ) % {
                    'cai': record.cai or _('Sin CAI'),
                    'ini': record.rangoInicial or 0,
                    'fin': record.rangoFinal or 0,
                    'desde': record.date_from or '—',
                    'hasta': record.date_to or '—',
                })
        return records

    def write(self, vals):
        self._check_fiscal_range_write_access(vals)

        tracked = {f: lbl for f, lbl in self._CHATTER_FIELDS.items() if f in vals}
        previous = {}
        audit_previous = {}
        if tracked:
            previous = {
                record.id: {f: record[f] for f in tracked}
                for record in self
            }
        if 'number_next_actual' in vals or 'number_next' in vals:
            audit_previous = {
                record.id: record.number_next
                for record in self.filtered(
                    lambda r: r.sequence_id and r.sequence_id.is_fiscal,
                )
            }

        write_vals = dict(vals)
        if (
            'rangoInicial' in write_vals
            and 'number_next' not in write_vals
            and 'number_next_actual' not in write_vals
            and len(self) == 1
        ):
            record = self
            new_ini = write_vals['rangoInicial']
            if (
                record.sequence_id.is_fiscal
                and new_ini
                and record.number_next < new_ini
            ):
                write_vals['number_next'] = new_ini
        if 'number_next_actual' in write_vals and 'number_next' not in write_vals:
            write_vals['number_next'] = write_vals['number_next_actual']
        if 'cai_validated' in write_vals:
            if write_vals['cai_validated']:
                write_vals.setdefault(
                    'cai_validation_date', fields.Datetime.now(),
                )
                write_vals['cai_validation_error'] = False
            else:
                write_vals['cai_validation_date'] = False
                write_vals['cai_validation_error'] = False

        result = super().write(write_vals)

        if {'number_next', 'number_next_actual'} & set(write_vals):
            fiscal_sequences = self.mapped('sequence_id').filtered('is_fiscal')
            if fiscal_sequences:
                fiscal_sequences.modified([
                    'date_range_ids.number_next',
                    'date_range_ids.number_next_actual',
                ])

        Audit = self.env['kc_fiscal_hn.sequence.audit']
        for record in self.filtered(
            lambda r: r.sequence_id and r.sequence_id.is_fiscal,
        ):
            old_number = audit_previous.get(record.id)
            if (
                old_number is not None
                and old_number != record.number_next
            ):
                Audit.create({
                    'sequence_id': record.sequence_id.id,
                    'action': 'modify',
                    'old_number': old_number,
                    'new_number': record.number_next,
                    'reason': _(
                        'Ajuste manual del correlativo en rango CAI %(cai)s.',
                        cai=record.cai or '',
                    ),
                    'user_id': self.env.user.id,
                })

        if tracked:
            for record in self:
                sequence = record.sequence_id
                if not sequence or not sequence.is_fiscal:
                    continue
                changes = []
                for field_name, label in tracked.items():
                    old = previous.get(record.id, {}).get(field_name)
                    new = record[field_name]
                    if old == new:
                        continue
                    if field_name == 'cai_validated':
                        old = _('Sí') if old else _('No')
                        new = _('Sí') if new else _('No')
                    changes.append(_(
                        '%(label)s: %(old)s → %(new)s',
                        label=label,
                        old=old if old not in (False, None) else '—',
                        new=new if new not in (False, None) else '—',
                    ))
                if changes:
                    sequence.message_post(
                        body=Markup('%s <b>%s</b>:<br/>%s') % (
                            _('Rango CAI'),
                            record.cai or _('Sin CAI'),
                            Markup('<br/>').join(
                                Markup('%s') % c for c in changes
                            ),
                        ),
                    )
        return result

    def unlink(self):
        fiscal_ranges = self.filtered(
            lambda r: r.sequence_id and r.sequence_id.is_fiscal,
        )
        if fiscal_ranges:
            if not self.env.user.has_group(
                'kc_fiscal_hn_v18.group_fiscal_sequence_manager',
            ):
                raise AccessError(_(
                    'Solo el Administrador de Numeración Fiscal puede '
                    'eliminar rangos CAI.',
                ))
            Audit = self.env['kc_fiscal_hn.sequence.audit']
            for record in fiscal_ranges:
                Audit.create({
                    'sequence_id': record.sequence_id.id,
                    'action': 'delete',
                    'old_number': record.number_next_actual,
                    'new_number': 0,
                    'reason': _(
                        'Eliminación del rango CAI %(cai)s (%(ini)s–%(fin)s).',
                        cai=record.cai or '',
                        ini=record.rangoInicial or 0,
                        fin=record.rangoFinal or 0,
                    ),
                    'user_id': self.env.user.id,
                })
                record.sequence_id.message_post(body=Markup(
                    _('Rango CAI eliminado: <b>%(cai)s</b> (%(ini)s–%(fin)s).')
                ) % {
                    'cai': record.cai or _('Sin CAI'),
                    'ini': record.rangoInicial or 0,
                    'fin': record.rangoFinal or 0,
                })
        return super().unlink()

    @api.constrains('number_next', 'rangoInicial', 'rangoFinal', 'sequence_id')
    def _check_number_next_in_range(self):
        for record in self:
            if not record.sequence_id.is_fiscal:
                continue
            next_number = record.number_next
            if not next_number:
                continue
            if record.rangoInicial and next_number < record.rangoInicial:
                raise ValidationError(_(
                    'El siguiente correlativo (%(next)s) no puede ser menor '
                    'al rango inicial (%(start)s).',
                    next=next_number,
                    start=record.rangoInicial,
                ))
            if record.rangoFinal and next_number > record.rangoFinal + 1:
                raise ValidationError(_(
                    'El siguiente correlativo (%(next)s) no puede superar '
                    'el rango final (%(end)s) en más de una unidad.',
                    next=next_number,
                    end=record.rangoFinal,
                ))

    @api.constrains('dias_alerta', 'numeros_alerta')
    def _check_range_alert_thresholds(self):
        for record in self:
            if record.dias_alerta is not None and record.dias_alerta < 0:
                raise ValidationError(_(
                    'Los días de alerta del rango CAI no pueden ser negativos.'
                ))
            if record.numeros_alerta is not None and record.numeros_alerta < 0:
                raise ValidationError(_(
                    'Los correlativos de alerta del rango CAI no pueden ser negativos.'
                ))

    def get_date_deadline_alert(self, document_date=None):
        """Alerta de vencimiento según dias_alerta de este rango CAI."""
        self.ensure_one()
        if not self.dias_alerta or not self.date_to:
            return None

        today = fields.Date.context_today(self)
        dias_restantes = (self.date_to - today).days
        if dias_restantes > self.dias_alerta:
            return None

        sequence = self.sequence_id
        if dias_restantes <= 0:
            if sequence.has_valid_future_sequences(document_date):
                return None
            return {
                'type': 'date',
                'blocking': True,
                'days_remaining': dias_restantes,
                'deadline': self.date_to,
                'message': _(
                    'La fecha límite de emisión (%(deadline)s) del CAI %(cai)s ha vencido '
                    'y no hay subsecuencias futuras. No se puede publicar la factura.',
                    deadline=self.date_to,
                    cai=self.cai or '',
                ),
            }

        return {
            'type': 'date',
            'blocking': False,
            'days_remaining': dias_restantes,
            'deadline': self.date_to,
            'message': _(
                'La fecha límite de emisión (%(deadline)s) del CAI vigente vence en '
                '%(days)d día(s). Alerta configurada en este rango: %(alert_days)d días '
                'antes del vencimiento.',
                deadline=self.date_to,
                days=dias_restantes,
                alert_days=self.dias_alerta,
            ),
        }

    def get_numbers_range_alert(self, document_date=None):
        """Alerta de correlativos según numeros_alerta de este rango CAI."""
        self.ensure_one()
        if not self.numeros_alerta or not self.rangoInicial or not self.rangoFinal:
            return None

        numeros_restantes = self.rangoFinal - self.number_next_actual + 1
        if numeros_restantes > self.numeros_alerta:
            return None

        sequence = self.sequence_id
        if numeros_restantes <= 0:
            if sequence.has_valid_future_sequences(document_date):
                return None
            return {
                'type': 'numbers',
                'blocking': True,
                'numbers_remaining': numeros_restantes,
                'message': _(
                    'El rango CAI %(start)d-%(end)d está agotado y no hay subsecuencias '
                    'futuras. No se puede publicar la factura.',
                    start=self.rangoInicial,
                    end=self.rangoFinal,
                ),
            }

        return {
            'type': 'numbers',
            'blocking': False,
            'numbers_remaining': numeros_restantes,
            'message': _(
                'Quedan %(remaining)d correlativo(s) del rango CAI %(start)d-%(end)d. '
                'Alerta configurada en este rango: %(alert_numbers)d restantes.',
                remaining=numeros_restantes,
                start=self.rangoInicial,
                end=self.rangoFinal,
                alert_numbers=self.numeros_alerta,
            ),
        }

    def check_cai_expiration(self):
        """
        CAI vencido o dentro del umbral dias_alerta (para wizard de alertas).
        """
        self.ensure_one()
        if not self.dias_alerta or not self.date_to:
            return None

        today = fields.Date.context_today(self)
        dias_restantes = (self.date_to - today).days
        if dias_restantes > self.dias_alerta:
            return None

        return {
            'sequence': self.sequence_id.name,
            'date_range': f'{self.date_from} — {self.date_to}',
            'cai': self.cai or '',
            'expiration_date': self.date_to,
            'days_to_expire': dias_restantes,
            'expired': dias_restantes <= 0,
        }

    @api.constrains('cai', 'sequence_id')
    def _check_cai_required(self):
        for record in self:
            if record.sequence_id.is_fiscal and not record.cai:
                raise ValidationError(_(
                    'El CAI es obligatorio en secuencias fiscales SAR.'
                ))

    @api.constrains('rangoInicial', 'rangoFinal', 'sequence_id')
    def _check_rangos_required(self):
        for record in self:
            if record.sequence_id.is_fiscal:
                if not record.rangoInicial or not record.rangoFinal:
                    raise ValidationError(_(
                        'El rango inicial y final son obligatorios '
                        'en secuencias fiscales SAR.'
                    ))

    @api.constrains('rangoInicial', 'rangoFinal')
    def _check_cai_ranges(self):
        """Validar que los rangos del CAI sean válidos"""
        for record in self:
            if record.rangoInicial and record.rangoFinal:
                if record.rangoInicial >= record.rangoFinal:
                    raise ValidationError(_('El rango inicial debe ser menor al rango final'))
                
                if record.rangoInicial < 1:
                    raise ValidationError(_('El rango inicial debe ser mayor a 0'))
    
    @api.constrains('date_from', 'date_to')
    def _check_date_ranges(self):
        """Validar que las fechas del rango sean válidas"""
        for record in self:
            if record.date_from and record.date_to:
                if record.date_from >= record.date_to:
                    raise ValidationError(_('La fecha de inicio debe ser menor a la fecha de fin'))
    
    # @api.constrains('cai')
    # def _check_cai_format(self):
    #     """Validar formato del CAI"""
    #     for record in self:
    #         if record.cai and not re.match(r'^[A-Z0-9]{37}$', record.cai):
    #             raise ValidationError(_('El CAI debe tener 37 caracteres alfanuméricos'))
    
    def validate_cai_manual(self):
        """Validar CAI manualmente (validaciones adicionales)"""
        self.ensure_one()
        
        try:
            # Validar que el CAI esté presente
            if not self.cai:
                raise ValidationError(_('El CAI no puede estar vacío'))
            
            # Las validaciones de formato, rangos y fechas se hacen automáticamente con constraints
            # Solo validar que todos los campos requeridos estén presentes
            if not self.rangoInicial or not self.rangoFinal:
                raise ValidationError(_('Los rangos inicial y final son obligatorios'))
            
            # Marcar como validado
            self.write({
                'cai_validated': True,
                'cai_validation_date': fields.Datetime.now(),
                'cai_validation_error': False
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Validación Exitosa'),
                    'message': _('El CAI ha sido validado correctamente'),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            self.write({
                'cai_validated': False,
                'cai_validation_date': fields.Datetime.now(),
                'cai_validation_error': str(e)
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error de Validación'),
                    'message': str(e),
                    'type': 'danger',
                }
            }
