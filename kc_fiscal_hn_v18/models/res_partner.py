# -*- coding: utf-8 -*-

import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

PAISES_CA = frozenset({'GT', 'SV', 'NI', 'CR', 'PA', 'BZ'})


class ResPartner(models.Model):
    _inherit = 'res.partner'

    vendedor_empleado = fields.Many2one('hr.employee', string='Vendedor Empleado', store=True)

    tipo_fiscal_proveedor = fields.Selection([
        ('nacional_empresa', 'Nacional — Empresa con RTN'),
        ('nacional_persona', 'Nacional — Persona Natural con RTN'),
        ('nacional_sin_rtn', 'Nacional — Sin RTN (Boleta)'),
        ('extranjero_ca', 'Extranjero — Centroamérica'),
        ('extranjero', 'Extranjero — Otros países'),
    ], string='Clasificación Fiscal',
       compute='_compute_tipo_fiscal_proveedor',
       store=True,
       help='Calculado automáticamente según país, '
            'RTN y tipo de contribuyente.',
    )
    diario_compra_sugerido_id = fields.Many2one(
        'account.journal',
        string='Diario Compra Sugerido',
        compute='_compute_diario_compra_sugerido',
        store=True,
        help='Diario sugerido automáticamente según '
             'la clasificación fiscal del proveedor.',
    )
    es_proveedor_materia_prima = fields.Boolean(
        string='Proveedor de materia prima (control DUCA)',
        default=False,
        tracking=True,
        help='Marque si es un proveedor extranjero de materia prima sujeta a '
             'control DUCA (Zona Libre). Sus compras se rutean al diario '
             'Importaciones (DUA/FYDUCA) en lugar de Compras Extranjera (FE).',
    )

    tiene_constancia_pago_cuenta = fields.Boolean(
        string='Tiene Constancia de Pago a Cuenta',
        default=False,
        tracking=True,
        help='Constancia emitida por el SAR Honduras '
             'que exime al proveedor de retenciones '
             'ISR (1% anticipo y 12.5% honorarios). '
             'Renovable cada cuatrimestre.',
    )
    numero_constancia_pago_cuenta = fields.Char(
        string='N° Constancia SAR',
        tracking=True,
    )
    fecha_vencimiento_constancia = fields.Date(
        string='Vence Constancia',
        tracking=True,
        help='Cuotas: 30 Jun, 30 Sep, 31 Dic.',
    )
    constancia_vigente = fields.Boolean(
        string='Constancia Vigente',
        compute='_compute_constancia_vigente',
        store=True,
    )
    dias_vencimiento_constancia = fields.Integer(
        string='Días para Vencer',
        compute='_compute_constancia_vigente',
        store=True,
    )
    imagen_constancia = fields.Binary(
        string='Constancia PDF/Imagen',
        help='Cargar PDF o imagen de la constancia '
             'de pago a cuenta emitida por el SAR.',
    )
    alerta_constancia = fields.Selection([
        ('ok', '✅ Vigente'),
        ('proximo', '⚠️ Próxima a vencer'),
        ('vencida', '🔴 Vencida'),
        ('sin_constancia', '— Sin constancia'),
    ], string='Estado Constancia',
       compute='_compute_constancia_vigente',
       store=True,
    )

    tiene_exoneracion_sar = fields.Boolean(
        string='Tiene Exoneración SAR',
        default=False,
        tracking=True,
        help='El cliente tiene Orden de Compra '
             'Exonerada (OCE) del SAR vigente.',
    )
    numero_exoneracion_sar = fields.Char(
        string='N° Constancia Exoneración',
        tracking=True,
    )
    fecha_vencimiento_exoneracion = fields.Date(
        string='Vence Exoneración',
        tracking=True,
    )
    exoneracion_vigente = fields.Boolean(
        string='Exoneración Vigente',
        compute='_compute_exoneracion_vigente',
        store=True,
    )
    dias_vencimiento_exoneracion = fields.Integer(
        string='Días para Vencer Exoneración',
        compute='_compute_exoneracion_vigente',
        store=True,
    )
    imagen_exoneracion = fields.Binary(
        string='Constancia Exoneración PDF',
    )
    alerta_exoneracion = fields.Selection([
        ('ok', '✅ Vigente'),
        ('proximo', '⚠️ Próxima a vencer'),
        ('vencida', '🔴 Vencida'),
        ('sin_exoneracion', '— Sin exoneración'),
    ], string='Estado Exoneración',
       compute='_compute_exoneracion_vigente',
       store=True,
    )

    @api.depends('country_id', 'vat', 'is_company')
    def _compute_tipo_fiscal_proveedor(self) -> None:
        for partner in self:
            if not partner.country_id:
                partner.tipo_fiscal_proveedor = False
                continue
            code = partner.country_id.code
            if code == 'HN':
                if partner.vat:
                    partner.tipo_fiscal_proveedor = (
                        'nacional_empresa' if partner.is_company
                        else 'nacional_persona'
                    )
                else:
                    partner.tipo_fiscal_proveedor = 'nacional_sin_rtn'
            elif code in PAISES_CA:
                partner.tipo_fiscal_proveedor = 'extranjero_ca'
            else:
                partner.tipo_fiscal_proveedor = 'extranjero'

    @api.depends('tipo_fiscal_proveedor', 'company_id', 'es_proveedor_materia_prima')
    def _compute_diario_compra_sugerido(self) -> None:
        Journal = self.env['account.journal']
        for partner in self:
            tipo = partner.tipo_fiscal_proveedor
            company = partner.company_id or self.env.company
            if tipo in ('nacional_empresa', 'nacional_persona'):
                doc_fiscal = 'vendors'
            elif tipo == 'nacional_sin_rtn':
                doc_fiscal = 'boleta'
            elif tipo in ('extranjero_ca', 'extranjero'):
                # Materia prima (Zona Libre) → control DUCA en Importaciones;
                # resto de proveedores extranjeros → Compras Extranjera (FE).
                doc_fiscal = (
                    'importacion' if partner.es_proveedor_materia_prima
                    else 'extranjera'
                )
            else:
                partner.diario_compra_sugerido_id = False
                continue
            partner.diario_compra_sugerido_id = Journal.search([
                ('document_fiscal', '=', doc_fiscal),
                ('company_id', '=', company.id),
            ], limit=1)

    @api.depends(
        'tiene_constancia_pago_cuenta',
        'fecha_vencimiento_constancia',
    )
    def _compute_constancia_vigente(self) -> None:
        today = fields.Date.context_today(self)
        for partner in self:
            if not partner.tiene_constancia_pago_cuenta:
                partner.constancia_vigente = False
                partner.dias_vencimiento_constancia = 0
                partner.alerta_constancia = 'sin_constancia'
                continue
            if not partner.fecha_vencimiento_constancia:
                partner.constancia_vigente = False
                partner.dias_vencimiento_constancia = 0
                partner.alerta_constancia = 'vencida'
                continue
            dias = (partner.fecha_vencimiento_constancia - today).days
            partner.dias_vencimiento_constancia = dias
            if dias < 0:
                partner.constancia_vigente = False
                partner.alerta_constancia = 'vencida'
            elif dias <= 30:
                partner.constancia_vigente = True
                partner.alerta_constancia = 'proximo'
            else:
                partner.constancia_vigente = True
                partner.alerta_constancia = 'ok'

    @api.depends(
        'tiene_exoneracion_sar',
        'fecha_vencimiento_exoneracion',
    )
    def _compute_exoneracion_vigente(self) -> None:
        today = fields.Date.context_today(self)
        for partner in self:
            if not partner.tiene_exoneracion_sar:
                partner.exoneracion_vigente = False
                partner.dias_vencimiento_exoneracion = 0
                partner.alerta_exoneracion = 'sin_exoneracion'
                continue
            if not partner.fecha_vencimiento_exoneracion:
                partner.exoneracion_vigente = False
                partner.dias_vencimiento_exoneracion = 0
                partner.alerta_exoneracion = 'vencida'
                continue
            dias = (partner.fecha_vencimiento_exoneracion - today).days
            partner.dias_vencimiento_exoneracion = dias
            if dias < 0:
                partner.exoneracion_vigente = False
                partner.alerta_exoneracion = 'vencida'
            elif dias <= 30:
                partner.exoneracion_vigente = True
                partner.alerta_exoneracion = 'proximo'
            else:
                partner.exoneracion_vigente = True
                partner.alerta_exoneracion = 'ok'

    @api.model
    def _cron_verificar_constancias(self) -> None:
        """Cron diario: alertas de constancias de pago a cuenta SAR."""
        today = fields.Date.today()
        fecha_alerta = today + timedelta(days=30)

        proximas = self.search([
            ('tiene_constancia_pago_cuenta', '=', True),
            ('fecha_vencimiento_constancia', '<=', fecha_alerta),
            ('fecha_vencimiento_constancia', '>=', today),
            ('active', '=', True),
        ])
        for partner in proximas:
            dias = (partner.fecha_vencimiento_constancia - today).days
            partner.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Constancia SAR vence en %d días') % dias,
                note=_(
                    'La constancia de pago a cuenta del proveedor '
                    '%(nombre)s vence el %(fecha)s. Solicite la '
                    'renovación para evitar retenciones ISR.',
                    nombre=partner.name,
                    fecha=partner.fecha_vencimiento_constancia,
                ),
                date_deadline=partner.fecha_vencimiento_constancia,
            )

        vencidas = self.search([
            ('tiene_constancia_pago_cuenta', '=', True),
            ('fecha_vencimiento_constancia', '<', today),
            ('active', '=', True),
        ])
        for partner in vencidas:
            partner.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Constancia SAR VENCIDA'),
                note=_(
                    'La constancia de pago a cuenta del proveedor '
                    '%(nombre)s venció el %(fecha)s. Las nuevas '
                    'facturas tendrán retención ISR.',
                    nombre=partner.name,
                    fecha=partner.fecha_vencimiento_constancia,
                ),
            )

    @api.model
    def _cron_alertas_exoneracion(self) -> None:
        """Cron diario: alertas de vencimiento de acuerdos de exoneración SAR.

        Notifica al responsable de zona (vendedor del cliente, con respaldo al
        responsable definido en la compañía) mediante una actividad To-Do,
        tanto para exoneraciones próximas a vencer como ya vencidas.
        Es idempotente: no duplica si ya existe una actividad de exoneración
        abierta sobre el contacto.
        """
        today = fields.Date.today()
        default_company = self.env.company

        candidatos = self.search([
            ('tiene_exoneracion_sar', '=', True),
            ('fecha_vencimiento_exoneracion', '!=', False),
            ('active', '=', True),
        ])
        for partner in candidatos:
            company = partner.company_id or default_company
            dias_alerta = company.exoneracion_dias_alerta or 30
            dias = (partner.fecha_vencimiento_exoneracion - today).days

            if dias < 0:
                estado = 'vencida'
            elif dias <= dias_alerta:
                estado = 'proxima'
            else:
                continue

            responsable = (
                partner.user_id
                or company.exoneracion_responsable_id
                or self.env.ref('base.user_root')
            )
            partner._exoneracion_programar_actividad(estado, dias, responsable)

    def _exoneracion_programar_actividad(self, estado, dias, responsable):
        """Crea (sin duplicar) la actividad de alerta de exoneración."""
        self.ensure_one()
        todo_type = self.env.ref('mail.mail_activity_data_todo')
        existente = self.env['mail.activity'].search([
            ('res_model', '=', 'res.partner'),
            ('res_id', '=', self.id),
            ('activity_type_id', '=', todo_type.id),
            ('summary', 'ilike', 'Exoneración SAR'),
        ], limit=1)
        if existente:
            return

        if estado == 'vencida':
            summary = _('Exoneración SAR VENCIDA')
            note = _(
                'El acuerdo de exoneración del cliente %(nombre)s venció el '
                '%(fecha)s. Solicite una nueva OCE al SAR antes de emitir '
                'facturas con impuesto exonerado.',
                nombre=self.name,
                fecha=self.fecha_vencimiento_exoneracion,
            )
            deadline = fields.Date.today()
        else:
            summary = _('Exoneración SAR vence en %d días') % dias
            note = _(
                'La exoneración SAR del cliente %(nombre)s vence el %(fecha)s. '
                'Gestione la renovación con el responsable de zona.',
                nombre=self.name,
                fecha=self.fecha_vencimiento_exoneracion,
            )
            deadline = self.fecha_vencimiento_exoneracion

        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=summary,
            note=note,
            date_deadline=deadline,
            user_id=responsable.id,
        )

    def _es_contacto_hijo_fiscal_hn(self):
        """True si el contacto hereda el RTN del contribuyente (no es la raíz).

        En Honduras el RTN pertenece al contribuyente (entidad comercial). Los
        contactos hijos y las direcciones (facturación/entrega) comparten el RTN
        de la empresa padre vía `commercial_partner_id`, por lo que no se validan
        de forma independiente.
        """
        self.ensure_one()
        commercial = self.commercial_partner_id
        return bool(commercial) and commercial != self

    @api.constrains('country_id', 'parent_id')
    def _check_country_id_required(self):
        """País obligatorio al crear o editar un contacto comercial raíz."""
        for partner in self:
            if partner._es_contacto_hijo_fiscal_hn():
                continue
            if not partner.country_id:
                raise ValidationError(_(
                    'El país es obligatorio al registrar un contacto.'
                ))

    @api.constrains('vat', 'country_id', 'is_company', 'parent_id')
    def _validate_rtn_required(self):
        for partner in self:
            # Sólo el contribuyente raíz requiere RTN propio; los hijos y
            # direcciones lo heredan de la empresa.
            if partner._es_contacto_hijo_fiscal_hn():
                continue
            if (
                partner.country_id
                and partner.country_id.code == 'HN'
                and partner.is_company
                and not partner.vat
            ):
                raise ValidationError(_(
                    'El RTN es obligatorio para empresas de Honduras.'
                ))

    @api.constrains('vat', 'country_id', 'is_company', 'parent_id')
    def _validate_rtn_format(self):
        for partner in self:
            if not partner.vat:
                continue
            if not partner.country_id or partner.country_id.code != 'HN':
                continue
            # Los contactos hijos/direcciones heredan el RTN del contribuyente;
            # la validación de formato y unicidad se hace sobre la entidad raíz.
            if partner._es_contacto_hijo_fiscal_hn():
                continue

            rtn = re.sub(r'[^0-9]', '', partner.vat)

            # RTN comodín (todo ceros) → contribuyente genérico tipo
            # "Consumidor Final" usado en ventas a consumidor final. No se
            # valida longitud ni unicidad para este placeholder.
            if rtn and set(rtn) == {'0'}:
                continue

            if partner.is_company:
                # Empresa / persona jurídica: RTN de 14 dígitos.
                longitudes_validas = (14,)
                tipo = 'empresa (persona jurídica)'
                detalle_longitud = '14 dígitos numéricos'
            else:
                # Persona natural: 13 dígitos (DNI).
                # Comerciante individual: 14 dígitos (nombre natural con RTN
                # de actividad comercial). Ambos se registran como persona.
                longitudes_validas = (13, 14)
                tipo = 'persona natural / comerciante individual'
                detalle_longitud = (
                    '13 dígitos (persona natural) o '
                    '14 dígitos (comerciante individual)'
                )

            if len(rtn) not in longitudes_validas:
                raise ValidationError(_(
                    'RTN inválido para %(tipo)s en Honduras.\n'
                    'Debe tener %(detalle)s.\n'
                    'RTN ingresado: %(rtn)s (%(actual)d dígitos)',
                    tipo=tipo,
                    detalle=detalle_longitud,
                    rtn=partner.vat,
                    actual=len(rtn),
                ))

            if not rtn.isdigit():
                raise ValidationError(_(
                    'El RTN solo debe contener dígitos numéricos (0-9).\n'
                    'RTN ingresado: %s'
                ) % partner.vat)

            # Unicidad por contribuyente: un RTN igual sólo es conflicto si
            # pertenece a una entidad comercial DISTINTA. Los contactos y
            # direcciones del mismo contribuyente (mismo commercial_partner_id)
            # comparten el RTN y no deben marcarse como duplicado.
            duplicado = self.env['res.partner'].search([
                ('country_id.code', '=', 'HN'),
                ('vat', '!=', False),
                ('commercial_partner_id', '!=', partner.id),
                ('active', 'in', [True, False]),
            ])
            for candidato in duplicado:
                if re.sub(r'[^0-9]', '', candidato.vat) == rtn:
                    entidad = candidato.commercial_partner_id or candidato
                    raise ValidationError(_(
                        'El RTN %(rtn)s ya está registrado en el '
                        'contribuyente: %(nombre)s.\n'
                        'El RTN debe ser único por contribuyente.',
                        rtn=partner.vat,
                        nombre=entidad.name,
                    ))

    def validate_rtn_manual(self):
        """Validar RTN manualmente desde el formulario de contacto."""
        self.ensure_one()
        if not self.vat:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin RTN'),
                    'message': _('Ingrese el RTN antes de validar.'),
                    'type': 'warning',
                },
            }
        try:
            self._validate_rtn_format()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('RTN Válido'),
                    'message': _('El RTN %s es válido y único.') % self.vat,
                    'type': 'success',
                },
            }
        except ValidationError as error:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('RTN Inválido'),
                    'message': str(error),
                    'type': 'danger',
                },
            }

    @api.onchange('vat', 'country_id', 'is_company')
    def _onchange_vat_rtn_hint(self):
        """Advertencia de formato RTN en formulario (sin bloquear edición)."""
        if not self.vat or not self.country_id or self.country_id.code != 'HN':
            return
        # Los contactos hijos/direcciones heredan el RTN del contribuyente.
        if self.parent_id:
            return

        rtn = re.sub(r'[^0-9]', '', self.vat)
        # RTN comodín (todo ceros): contribuyente genérico (Consumidor Final).
        if rtn and set(rtn) == {'0'}:
            return
        if self.is_company:
            longitudes_validas = (14,)
            tipo = _('empresa')
            detalle_longitud = _('14 dígitos')
        else:
            longitudes_validas = (13, 14)
            tipo = _('persona natural / comerciante individual')
            detalle_longitud = _(
                '13 dígitos (persona natural) o 14 (comerciante individual)'
            )

        if len(rtn) not in longitudes_validas:
            return {
                'warning': {
                    'title': _('RTN Honduras'),
                    'message': _(
                        'RTN de %(tipo)s: debe tener %(len)s numéricos '
                        '(sin guiones). Ingresados: %(actual)d.',
                        tipo=tipo,
                        len=detalle_longitud,
                        actual=len(rtn),
                    ),
                },
            }

    @api.model
    def _sincronizar_is_company_hn(self, vals):
        """Garantiza coherencia entre `company_type` e `is_company`.

        La app Contactos abre los registros nuevos con `default_is_company=True`.
        Al elegir "Persona" (company_type='person') ese default del contexto
        puede prevalecer y dejar `is_company=True`, clasificando erróneamente a
        las personas naturales como empresas (exigiéndoles RTN de 14 dígitos).
        Cuando `company_type` viene explícito en los valores, forzamos
        `is_company` para que refleje siempre lo que el usuario eligió.
        """
        if vals.get('company_type'):
            vals['is_company'] = vals['company_type'] == 'company'

    # ── Referencia interna autogenerada por tipo de contacto ──────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sincronizar_is_company_hn(vals)
        partners = super().create(vals_list)
        for partner in partners:
            partner._asignar_ref_fiscal_hn()
        return partners

    def write(self, vals):
        self._sincronizar_is_company_hn(vals)
        return super().write(vals)

    def _ref_secuencia_code_fiscal_hn(self):
        """Código de secuencia de referencia según el tipo de contacto raíz.

        - Empresa nacional (HN o sin país) → EMPNAC####
        - Empresa extranjera              → EMPEXT####
        - Persona natural                 → CONTAC-####
        """
        self.ensure_one()
        if self.is_company:
            code = self.country_id.code if self.country_id else False
            if not code or code == 'HN':
                return 'kc_fiscal_hn.partner.empnac'
            return 'kc_fiscal_hn.partner.empext'
        return 'kc_fiscal_hn.partner.contac'

    def _asignar_ref_fiscal_hn(self):
        """Genera la referencia interna para contactos raíz que no la tengan.

        Se omite cuando:
        - El contexto pide saltarlo (p.ej. sincronización desde empleado).
        - Ya tiene `ref`.
        - Es un contacto hijo o dirección (`parent_id` o `type != 'contact'`):
          direcciones y contactos dentro de una empresa NO llevan código.
        - El contacto es la empresa propia (res.company).
        """
        self.ensure_one()
        if self.env.context.get('skip_partner_ref_fiscal_hn'):
            return
        if self.ref:
            return
        if self.parent_id:
            return
        if self.type and self.type != 'contact':
            return
        if self.env['res.company'].sudo().search_count(
            [('partner_id', '=', self.id)]
        ):
            return
        code = self._ref_secuencia_code_fiscal_hn()
        Sequence = self.env['ir.sequence'].sudo()
        nueva_ref = Sequence.next_by_code(code)
        # Defensa ante colisiones con referencias preexistentes (p.ej. cargadas
        # manualmente): avanzar la secuencia hasta obtener un valor libre.
        intentos = 0
        while nueva_ref and intentos < 50 and self.with_context(
            active_test=False
        ).search_count([('ref', '=ilike', nueva_ref)]):
            nueva_ref = Sequence.next_by_code(code)
            intentos += 1
        if nueva_ref:
            self.with_context(skip_partner_ref_fiscal_hn=True).ref = nueva_ref

    @api.constrains('ref')
    def _check_ref_unico_fiscal_hn(self):
        """Impide duplicar la referencia interna entre contactos."""
        for partner in self:
            if not partner.ref:
                continue
            ref = partner.ref.strip()
            if not ref:
                continue
            duplicado = self.with_context(active_test=False).search([
                ('id', '!=', partner.id),
                ('ref', '=ilike', ref),
            ], limit=1)
            if duplicado:
                raise ValidationError(_(
                    'La referencia interna "%(ref)s" ya está asignada al '
                    'contacto "%(nombre)s". La referencia debe ser única.',
                    ref=partner.ref,
                    nombre=duplicado.display_name,
                ))

    @api.model
    def _init_refs_fiscal_hn(self):
        """Asigna referencia a los contactos raíz existentes sin `ref`.

        Idempotente: sólo afecta contactos sin referencia. Se invoca desde los
        datos del módulo en cada actualización.
        """
        pendientes = self.search([
            ('ref', '=', False),
            ('parent_id', '=', False),
            ('type', '=', 'contact'),
        ])
        for partner in pendientes:
            partner._asignar_ref_fiscal_hn()
