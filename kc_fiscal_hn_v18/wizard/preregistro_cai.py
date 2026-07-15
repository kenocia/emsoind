# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PreregistroCAI(models.TransientModel):
    _name = 'kc_fiscal_hn.wizard.preregistro_cai'
    _description = 'Preregistro de Numeración CAI SAR'

    paso_actual = fields.Integer(default=1)

    sequence_id = fields.Many2one(
        'ir.sequence',
        string='Secuencia Fiscal',
        domain="[('is_fiscal', '=', True)]",
        required=True,
    )

    bloquear_secuencia = fields.Boolean(
        string='Secuencia fija',
        default=False,
        readonly=True,
    )

    paso_1_label = fields.Char(
        compute='_compute_paso_labels',
    )
    paso_2_label = fields.Char(
        compute='_compute_paso_labels',
    )
    paso_3_label = fields.Char(
        compute='_compute_paso_labels',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('from_fiscal_sequence_form'):
            res['bloquear_secuencia'] = True
        if self.env.context.get('default_sequence_id'):
            res['sequence_id'] = self.env.context['default_sequence_id']
        return res

    @api.depends('bloquear_secuencia')
    def _compute_paso_labels(self):
        for wiz in self:
            if wiz.bloquear_secuencia:
                wiz.paso_1_label = _('Encabezado')
                wiz.paso_2_label = _('Detalle CAI')
                wiz.paso_3_label = _('Validación')
            else:
                wiz.paso_1_label = _('Secuencia')
                wiz.paso_2_label = _('Datos CAI')
                wiz.paso_3_label = _('Confirmar')

    rango_actual_cai = fields.Char(
        string='CAI Actual',
        compute='_compute_info_actual',
    )
    rango_actual_desde = fields.Date(
        compute='_compute_info_actual',
    )
    rango_actual_hasta = fields.Date(
        compute='_compute_info_actual',
    )
    rango_actual_inicial = fields.Integer(
        compute='_compute_info_actual',
    )
    rango_actual_final = fields.Integer(
        compute='_compute_info_actual',
    )
    rango_actual_siguiente = fields.Integer(
        compute='_compute_info_actual',
    )
    rango_actual_disponibles = fields.Integer(
        compute='_compute_info_actual',
    )
    rango_actual_total = fields.Integer(
        compute='_compute_info_actual',
    )
    rango_actual_porcentaje = fields.Float(
        compute='_compute_info_actual',
    )
    rango_actual_dias = fields.Integer(
        compute='_compute_info_actual',
    )
    estado_actual = fields.Selection([
        ('active', 'Activo'),
        ('warning', 'Advertencia'),
        ('critical', 'Crítico'),
        ('expired', 'Expirado'),
        ('sin_rango', 'Sin rango activo'),
    ], compute='_compute_info_actual')

    nuevo_cai = fields.Char(
        string='Nuevo CAI',
    )
    nuevo_desde = fields.Date(
        string='Válido desde',
    )
    nuevo_hasta = fields.Date(
        string='Fecha límite emisión',
    )
    nuevo_rango_inicial = fields.Integer(
        string='Correlativo inicial',
    )
    nuevo_rango_final = fields.Integer(
        string='Correlativo final',
    )
    activacion = fields.Selection([
        ('auto', 'Automática (recomendado)'),
        ('manual', 'Manual'),
    ], string='Tipo de activación',
       default='auto',
       required=True,
    )

    preview_primer_correlativo = fields.Char(
        compute='_compute_preview',
    )
    preview_ultimo_correlativo = fields.Char(
        compute='_compute_preview',
    )
    preview_total_disponibles = fields.Integer(
        compute='_compute_preview',
    )
    validacion_cai_ok = fields.Boolean(
        compute='_compute_validaciones',
    )
    validacion_rango_ok = fields.Boolean(
        compute='_compute_validaciones',
    )
    validacion_fecha_ok = fields.Boolean(
        compute='_compute_validaciones',
    )
    validacion_mensaje = fields.Text(
        compute='_compute_validaciones',
    )
    puede_confirmar = fields.Boolean(
        compute='_compute_validaciones',
    )

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda s: s.env.company.currency_id,
    )

    @api.depends('sequence_id')
    def _compute_info_actual(self) -> None:
        today = fields.Date.today()
        for wiz in self:
            if not wiz.sequence_id:
                wiz.rango_actual_cai = ''
                wiz.rango_actual_desde = False
                wiz.rango_actual_hasta = False
                wiz.rango_actual_inicial = 0
                wiz.rango_actual_final = 0
                wiz.rango_actual_siguiente = 0
                wiz.rango_actual_disponibles = 0
                wiz.rango_actual_total = 0
                wiz.rango_actual_porcentaje = 0
                wiz.rango_actual_dias = 0
                wiz.estado_actual = 'sin_rango'
                continue

            seq = wiz.sequence_id
            current = seq._fiscal_active_date_ranges_on(today)

            if not current:
                wiz.rango_actual_cai = 'Sin rango activo'
                wiz.rango_actual_desde = False
                wiz.rango_actual_hasta = False
                wiz.rango_actual_inicial = 0
                wiz.rango_actual_final = 0
                wiz.rango_actual_siguiente = 0
                wiz.rango_actual_disponibles = 0
                wiz.rango_actual_total = 0
                wiz.rango_actual_porcentaje = 0
                wiz.rango_actual_dias = 0
                wiz.estado_actual = 'sin_rango'
                continue

            r = current[0]
            total = max(1, r.rangoFinal - r.rangoInicial + 1)
            next_number = r.number_next_actual or r.number_next or r.rangoInicial
            usados = max(0, next_number - r.rangoInicial)
            disponibles = max(0, r.rangoFinal - next_number + 1)
            dias = (r.date_to - today).days if r.date_to else 0
            dias_alerta = r.dias_alerta or seq.default_dias_alerta or 5
            numeros_alerta = r.numeros_alerta or seq.default_numeros_alerta or 10

            wiz.rango_actual_cai = r.cai or ''
            wiz.rango_actual_desde = r.date_from
            wiz.rango_actual_hasta = r.date_to
            wiz.rango_actual_inicial = r.rangoInicial
            wiz.rango_actual_final = r.rangoFinal
            wiz.rango_actual_siguiente = next_number
            wiz.rango_actual_disponibles = disponibles
            wiz.rango_actual_total = total
            wiz.rango_actual_porcentaje = usados / total * 100
            wiz.rango_actual_dias = dias

            if dias < 0:
                wiz.estado_actual = 'expired'
            elif disponibles <= 0:
                wiz.estado_actual = 'critical'
            elif dias <= dias_alerta or (
                numeros_alerta > 0
                and disponibles < total
                and disponibles <= numeros_alerta
            ):
                wiz.estado_actual = 'warning'
            else:
                wiz.estado_actual = 'active'

    @api.depends(
        'sequence_id',
        'nuevo_rango_inicial',
        'nuevo_rango_final',
        'nuevo_desde',
    )
    def _compute_preview(self) -> None:
        for wiz in self:
            if not wiz.sequence_id or not wiz.nuevo_rango_inicial:
                wiz.preview_primer_correlativo = ''
                wiz.preview_ultimo_correlativo = ''
                wiz.preview_total_disponibles = 0
                continue
            seq = wiz.sequence_id
            pad = seq.padding or 8
            prefix = seq.prefix or ''
            year = (
                wiz.nuevo_desde.year
                if wiz.nuevo_desde
                else fields.Date.today().year
            )
            prefix_real = prefix.replace('%(range_year)s', str(year))
            wiz.preview_primer_correlativo = (
                f"{prefix_real}{str(wiz.nuevo_rango_inicial).zfill(pad)}"
            )
            wiz.preview_ultimo_correlativo = (
                f"{prefix_real}{str(wiz.nuevo_rango_final).zfill(pad)}"
            )
            wiz.preview_total_disponibles = max(
                0,
                wiz.nuevo_rango_final - wiz.nuevo_rango_inicial + 1,
            )

    @api.depends(
        'nuevo_cai',
        'nuevo_rango_inicial',
        'nuevo_rango_final',
        'nuevo_desde',
        'nuevo_hasta',
        'rango_actual_final',
        'rango_actual_hasta',
        'preview_total_disponibles',
    )
    def _compute_validaciones(self) -> None:
        for wiz in self:
            mensajes = []
            cai_ok = rango_ok = fecha_ok = True

            if wiz.nuevo_cai and len(wiz.nuevo_cai) < 10:
                cai_ok = False
                mensajes.append(
                    '❌ CAI demasiado corto (mínimo 10 caracteres)'
                )
            elif wiz.nuevo_cai:
                mensajes.append('✅ CAI con formato correcto')

            if wiz.nuevo_rango_inicial and wiz.nuevo_rango_final:
                if wiz.nuevo_rango_inicial >= wiz.nuevo_rango_final:
                    rango_ok = False
                    mensajes.append(
                        '❌ El rango inicial debe ser menor al final'
                    )
                elif (
                    wiz.rango_actual_final
                    and wiz.nuevo_rango_inicial <= wiz.rango_actual_final
                ):
                    rango_ok = False
                    mensajes.append(
                        f'❌ El rango inicial debe ser mayor a '
                        f'{wiz.rango_actual_final} '
                        f'(último del CAI actual)'
                    )
                else:
                    mensajes.append(
                        f'✅ Rango válido: '
                        f'{wiz.preview_total_disponibles} '
                        f'correlativos disponibles'
                    )

            if wiz.nuevo_desde and wiz.nuevo_hasta:
                if wiz.nuevo_desde >= wiz.nuevo_hasta:
                    fecha_ok = False
                    mensajes.append(
                        '❌ La fecha inicio debe ser menor a fecha límite'
                    )
                elif (
                    wiz.rango_actual_hasta
                    and wiz.nuevo_desde <= wiz.rango_actual_hasta
                ):
                    mensajes.append(
                        f'⚠️ La fecha inicio ({wiz.nuevo_desde}) '
                        f'se solapa con el CAI actual '
                        f'(vence {wiz.rango_actual_hasta}). '
                        f'Se activará automáticamente al vencer.'
                    )
                else:
                    mensajes.append(
                        f'✅ Fechas válidas: '
                        f'{wiz.nuevo_desde} al {wiz.nuevo_hasta}'
                    )

            wiz.validacion_cai_ok = cai_ok
            wiz.validacion_rango_ok = rango_ok
            wiz.validacion_fecha_ok = fecha_ok
            wiz.validacion_mensaje = '\n'.join(mensajes)
            wiz.puede_confirmar = all([
                wiz.nuevo_cai,
                wiz.nuevo_desde,
                wiz.nuevo_hasta,
                wiz.nuevo_rango_inicial,
                wiz.nuevo_rango_final,
                cai_ok,
                rango_ok,
                fecha_ok,
            ])

    def action_paso_siguiente(self):
        self.ensure_one()
        if self.paso_actual == 1 and not self.sequence_id:
            raise UserError(_('Seleccione una secuencia fiscal.'))
        if self.paso_actual == 2:
            if not all([
                self.nuevo_cai,
                self.nuevo_desde,
                self.nuevo_hasta,
                self.nuevo_rango_inicial,
                self.nuevo_rango_final,
            ]):
                raise UserError(_(
                    'Complete todos los datos del nuevo CAI antes de continuar.'
                ))
        if self.paso_actual < 3:
            self.paso_actual += 1
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_paso_anterior(self):
        self.ensure_one()
        if self.paso_actual > 1:
            self.paso_actual -= 1
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirmar_preregistro(self):
        """Crea el nuevo rango CAI preregistrado (activación por cron)."""
        self.ensure_one()

        if not self.puede_confirmar:
            raise UserError(_(
                'Corrija los errores de validación '
                'antes de confirmar el preregistro.'
            ))

        self.env['ir.sequence.date_range'].create({
            'sequence_id': self.sequence_id.id,
            'date_from': self.nuevo_desde,
            'date_to': self.nuevo_hasta,
            'cai': self.nuevo_cai,
            'rangoInicial': self.nuevo_rango_inicial,
            'rangoFinal': self.nuevo_rango_final,
            'number_next': self.nuevo_rango_inicial,
            'cai_validated': True,
            'cai_validation_date': fields.Datetime.now(),
        })

        self.env['kc_fiscal_hn.sequence.audit'].create({
            'sequence_id': self.sequence_id.id,
            'action': 'create',
            'old_number': 0,
            'new_number': self.nuevo_rango_inicial,
            'reason': (
                f'Preregistro CAI {self.nuevo_cai} '
                f'rango {self.nuevo_rango_inicial}-'
                f'{self.nuevo_rango_final} '
                f'vigente {self.nuevo_desde} al '
                f'{self.nuevo_hasta}'
            ),
            'user_id': self.env.user.id,
        })

        if self.env.context.get('from_fiscal_sequence_form'):
            return {
                'type': 'ir.actions.act_window',
                'name': self.sequence_id.name,
                'res_model': 'ir.sequence',
                'res_id': self.sequence_id.id,
                'view_mode': 'form',
                'views': [(
                    self.env.ref(
                        'kc_fiscal_hn_v18.ir_sequence_fiscal_form',
                    ).id,
                    'form',
                )],
                'target': 'current',
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('✅ CAI Preregistrado'),
                'message': _(
                    'El CAI %s fue preregistrado '
                    'correctamente para la secuencia %s.\n'
                    'Se activará automáticamente cuando '
                    'el rango actual se agote o venza.'
                ) % (self.nuevo_cai, self.sequence_id.name),
                'type': 'success',
                'sticky': True,
            },
        }
