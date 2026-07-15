# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import formatLang


class ResCompany(models.Model):
    _inherit = 'res.company'

    rtn_empresa = fields.Char(
        string='RTN Empresa',
        related='vat',
        store=True,
        readonly=True,
        help='RTN de la empresa. Es el MISMO RTN nativo de Odoo (campo "RTN" / '
             '"vat" en la pestaña Información general); se conserva aquí solo '
             'por compatibilidad. No se captura por separado.',
    )
    fiscal_resolution = fields.Char(
        string='Resolución SAR',
        help='Número de resolución SAR de la empresa',
    )
    fiscal_resolution_date = fields.Date(
        string='Fecha Resolución SAR',
        help='Fecha de la resolución SAR de la empresa',
    )
    banking_information_image = fields.Binary(
        string='Información Bancaria',
        help='Imagen con la información bancaria de la compañía para mostrar en reportes',
    )
    terms_conditions_image = fields.Binary(
        string='Términos y Condiciones',
        help='Imagen con los términos y condiciones de la compañía para mostrar en reportes',
    )

    # ── Clasificación SAR ─────────────────────────────────
    tipo_contribuyente = fields.Selection([
        ('pequeno', 'Pequeño Contribuyente'),
        ('mediano', 'Mediano Contribuyente'),
        ('grande', 'Grande Contribuyente'),
    ], string='Clasificación SAR Honduras',
       default='pequeno',
       required=True,
       tracking=True,
       help='Clasificación según SAR Honduras '
            '(Acuerdo SAR-125-2022).\n\n'
            'PEQUEÑO: No obligado a DMC.\n'
            'MEDIANO: Obligado a DMC mensual.\n'
            'GRANDE: Obligado a DMC + agente '
            'de retención ISV 15%.',
    )

    # ── Campos compute en cascada ────────────────────────
    obligado_dmc = fields.Boolean(
        string='Obligado a presentar DMC',
        compute='_compute_obligaciones_fiscales',
        store=True,
        help='Los contribuyentes medianos y grandes '
             'deben presentar la Declaración Mensual '
             'de Compras en los primeros 8 días '
             'hábiles del mes siguiente.',
    )
    es_agente_retencion = fields.Boolean(
        string='Agente de Retención ISV',
        compute='_compute_obligaciones_fiscales',
        store=True,
        help='Solo los grandes contribuyentes '
             'retienen el 15% ISV en servicios de '
             'transporte, alquiler y maquinaria.',
    )
    requiere_libro_dmc = fields.Boolean(
        string='Requiere Libro DMC Completo',
        compute='_compute_obligaciones_fiscales',
        store=True,
    )
    nivel_control_fiscal = fields.Selection([
        ('basico', 'Control Básico'),
        ('intermedio', 'Control Intermedio (DMC)'),
        ('completo', 'Control Completo (DMC + Retención)'),
    ], string='Nivel de Control Fiscal',
       compute='_compute_obligaciones_fiscales',
       store=True,
    )

    # ── Información SAR adicional ────────────────────────
    numero_contribuyente_sar = fields.Char(
        string='N° Contribuyente SAR',
        help='Número asignado por el SAR Honduras.',
    )
    regimen_especial = fields.Boolean(
        string='Régimen Especial',
        default=False,
        help='Si está en régimen especial también '
             'está obligado a presentar DMC.',
    )
    fecha_clasificacion_sar = fields.Date(
        string='Fecha Clasificación SAR',
        help='Fecha en que el SAR clasificó al '
             'contribuyente en su categoría actual.',
    )

    # ── Diarios por defecto (nuevos movimientos contables) ──
    fiscal_default_sale_journal_id = fields.Many2one(
        'account.journal',
        string='Diario facturas clientes',
        check_company=True,
        domain="[('type', '=', 'sale'), ('document_fiscal', '=', 'client')]",
        help='Diario predeterminado al crear facturas de cliente.',
    )
    fiscal_default_sale_refund_journal_id = fields.Many2one(
        'account.journal',
        string='Diario NC clientes',
        check_company=True,
        domain="[('type', '=', 'sale'), ('document_fiscal', 'in', ('client', 'credit'))]",
        help='Diario predeterminado al crear notas de crédito de cliente.',
    )
    fiscal_default_purchase_journal_id = fields.Many2one(
        'account.journal',
        string='Diario facturas proveedores',
        check_company=True,
        domain="[('type', '=', 'purchase'), ('document_fiscal', '=', 'vendors')]",
        help='Diario predeterminado al crear facturas de proveedor (FA).',
    )
    fiscal_default_purchase_refund_journal_id = fields.Many2one(
        'account.journal',
        string='Diario NC proveedores',
        check_company=True,
        domain="[('type', '=', 'purchase'), ('document_fiscal', '=', 'credit')]",
        help='Diario predeterminado al crear notas de crédito de proveedor.',
    )
    fiscal_default_misc_journal_id = fields.Many2one(
        'account.journal',
        string='Diario asientos directos',
        check_company=True,
        domain="[('type', '=', 'general')]",
        help='Diario predeterminado al crear asientos contables (operaciones varias).',
    )

    # ── Control de exoneración al facturar ───────────────
    exoneracion_modo_control = fields.Selection([
        ('ninguno', 'Sin control'),
        ('advertencia', 'Advertencia (permite continuar)'),
        ('bloqueo', 'Bloqueo duro (impide confirmar)'),
    ], string='Control de exoneración al facturar',
       default='advertencia',
       required=True,
       help='Comportamiento al confirmar una factura de venta con impuesto '
            'exonerado cuando el acuerdo de exoneración del cliente está '
            'vencido o no es válido.\n\n'
            'SIN CONTROL: no valida nada.\n'
            'ADVERTENCIA: avisa al facturista pero deja continuar.\n'
            'BLOQUEO DURO: impide confirmar (salvo el Gerente fiscal).',
    )
    exoneracion_dias_alerta = fields.Integer(
        string='Días de alerta de vencimiento (exoneración)',
        default=30,
        help='Días antes del vencimiento del acuerdo de exoneración para '
             'notificar al responsable de zona mediante una actividad.',
    )
    exoneracion_responsable_id = fields.Many2one(
        'res.users',
        string='Responsable de zona (respaldo)',
        help='Usuario que recibe las alertas de exoneración cuando el cliente '
             'no tiene vendedor asignado.',
    )

    # ── Control de monto para "Consumidor Final" ─────────
    consumidor_final_control_activo = fields.Boolean(
        string='Controlar monto de Consumidor Final',
        default=True,
        help='Activa el bloqueo de órdenes de venta y facturas a nombre del '
             'contacto "Consumidor Final" cuyo total supere el monto máximo '
             'permitido.',
    )
    consumidor_final_partner_id = fields.Many2one(
        'res.partner',
        string='Contacto Consumidor Final',
        help='Contacto genérico utilizado para ventas a Consumidor Final. '
             'Las ventas a este contacto no pueden superar el monto máximo.',
    )
    consumidor_final_monto_maximo = fields.Monetary(
        string='Monto máximo Consumidor Final',
        currency_field='currency_id',
        help='Monto máximo (impuestos incluidos, en moneda de la compañía) '
             'permitido por documento para el contacto Consumidor Final. '
             'Dejar en 0 para no aplicar el límite.',
    )

    # ── Régimen de Zona Libre (ZOLI) ─────────────────────
    es_zoli = fields.Boolean(
        string='Empresa bajo régimen de Zona Libre (ZOLI)',
        default=False,
        tracking=True,
        help='Activa los controles del régimen de Zona Libre (ZOLI):\n'
             '- Control de permanencia de materia prima importada (DUCA).\n'
             '- Nacionalización (DAI + ISV) en ventas locales.\n'
             '- Control del límite de ventas locales anuales.\n\n'
             'Si está desactivado, la compañía opera bajo el régimen normal '
             'sin ninguno de estos controles.',
    )
    duca_dias_permanencia = fields.Integer(
        string='Días de permanencia DUCA',
        default=180,
        help='Días máximos de permanencia de la materia prima importada bajo '
             'régimen de Zona Libre antes de su vencimiento. La fecha de '
             'vencimiento del lote DUCA se calcula como fecha de recepción + '
             'estos días.',
    )
    duca_dias_alerta_previa = fields.Integer(
        string='Días de alerta previa DUCA',
        default=30,
        help='Días antes del vencimiento del lote DUCA para enviar la primera '
             'alerta a compras y bodega.',
    )
    duca_dias_alerta_critica = fields.Integer(
        string='Días de alerta crítica DUCA',
        default=7,
        help='Días antes del vencimiento del lote DUCA para enviar la alerta '
             'crítica con notificación por correo a los responsables.',
    )
    duca_responsable_compras_id = fields.Many2one(
        'res.users',
        string='Responsable de Compras (ZOLI)',
        help='Usuario de compras que recibe las alertas de vencimiento de '
             'lotes DUCA.',
    )
    duca_responsable_bodega_id = fields.Many2one(
        'res.users',
        string='Responsable de Bodega (ZOLI)',
        help='Usuario de bodega que recibe las alertas de vencimiento de '
             'lotes DUCA.',
    )
    duca_modo_vencidos = fields.Selection([
        ('advertencia', 'Advertencia (permite continuar)'),
        ('bloqueo', 'Bloqueo duro (impide usar el lote)'),
    ], string='Control de lotes DUCA vencidos',
       default='bloqueo',
       required=True,
       help='Comportamiento al intentar usar (salida/consumo) un lote DUCA '
            'vencido sin autorización de gerencia.\n\n'
            'ADVERTENCIA: registra un aviso pero permite continuar.\n'
            'BLOQUEO DURO: impide la operación (salvo autorización expresa de '
            'gerencia en el lote).',
    )
    zoli_limite_local_pct = fields.Float(
        string='Límite de ventas locales (%)',
        default=50.0,
        help='Porcentaje máximo de ventas locales (nacionalizadas) permitido '
             'sobre el total de ventas anuales para una empresa ZOLI. Por ley '
             'el máximo es 50%.',
    )
    zoli_limite_alerta_pct = fields.Float(
        string='Umbral de alerta de ventas locales (%)',
        default=45.0,
        help='Porcentaje de ventas locales a partir del cual el Dashboard '
             'Fiscal muestra una alerta de proximidad al límite legal.',
    )

    def check_consumidor_final_limit(self, partner, amount_total,
                                     currency=None, document=None):
        """Bloquea ventas a Consumidor Final que superan el monto máximo.

        Aplica un bloqueo duro (sin excepción): si el documento es a nombre
        del contacto Consumidor Final configurado y su total supera el límite,
        se registra el intento en auditoría y se lanza UserError.
        """
        self.ensure_one()
        if not self.consumidor_final_control_activo:
            return
        cf_partner = self.consumidor_final_partner_id
        limite = self.consumidor_final_monto_maximo
        if not cf_partner or limite <= 0 or not partner:
            return

        partners = partner | partner.commercial_partner_id
        if cf_partner.id not in partners.ids:
            return

        company_currency = self.currency_id
        monto = amount_total
        if currency and company_currency and currency != company_currency:
            monto = currency._convert(
                amount_total, company_currency, self,
                fields.Date.context_today(self),
            )

        if monto <= limite:
            return

        self.env['kc_fiscal_hn.consumidor.final.audit'].registrar_bloqueo(
            partner=partner, document=document, monto=monto,
            monto_maximo=limite, company=self,
        )
        raise UserError(_(
            'No es posible continuar con el cliente «Consumidor Final».\n\n'
            'El monto del documento (%(monto)s) supera el máximo permitido '
            'para Consumidor Final (%(limite)s).\n\n'
            'Para continuar debe registrar un contacto formal con RTN y '
            'asignarlo en el documento.',
            monto=formatLang(self.env, monto, currency_obj=company_currency),
            limite=formatLang(self.env, limite, currency_obj=company_currency),
        ))

    @api.depends('tipo_contribuyente', 'regimen_especial')
    def _compute_obligaciones_fiscales(self):
        """
        Calcula en cascada todas las obligaciones
        fiscales según el tipo de contribuyente.
        UN SOLO método controla todo.
        """
        for company in self:
            tipo = company.tipo_contribuyente
            especial = company.regimen_especial

            company.obligado_dmc = (
                tipo in ('mediano', 'grande') or especial
            )
            company.es_agente_retencion = tipo == 'grande'
            company.requiere_libro_dmc = (
                tipo in ('mediano', 'grande') or especial
            )

            if tipo == 'grande':
                company.nivel_control_fiscal = 'completo'
            elif tipo == 'mediano' or especial:
                company.nivel_control_fiscal = 'intermedio'
            else:
                company.nivel_control_fiscal = 'basico'

    @api.onchange('tipo_contribuyente')
    def _onchange_tipo_contribuyente(self):
        """Muestra mensaje informativo al cambiar el tipo de contribuyente."""
        if self.tipo_contribuyente == 'mediano':
            return {
                'warning': {
                    'title': 'Mediano Contribuyente',
                    'message': (
                        'Como mediano contribuyente debe '
                        'presentar la DMC mensualmente en '
                        'los primeros 8 días hábiles del '
                        'mes siguiente.\n\n'
                        'El módulo activará automáticamente '
                        'el Libro de Compras DMC completo.'
                    ),
                },
            }
        if self.tipo_contribuyente == 'grande':
            return {
                'warning': {
                    'title': 'Grande Contribuyente',
                    'message': (
                        'Como grande contribuyente debe:\n'
                        '1. Presentar DMC mensualmente\n'
                        '2. Retener 15% ISV en servicios\n\n'
                        'El módulo activará el Libro DMC '
                        'completo y el control de '
                        'retenciones ISV.'
                    ),
                },
            }
