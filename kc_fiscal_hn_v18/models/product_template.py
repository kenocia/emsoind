# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Campos del módulo original
    exento = fields.Boolean(string='Exento', required=False, default=False)
    is_retention = fields.Boolean(string='Es Retención', default=False)
    tax_retention = fields.Many2one(comodel_name='account.tax', string='Impuesto Retención',
                                    required=False)

    # Campos fiscales para productos (del módulo migrado)
    codigo_sar = fields.Char(string='Código SAR', help='Código del producto según SAR')
    es_exento = fields.Boolean(string='Es Exento', default=False,
                              help='Indica si el producto está exento de impuestos')
    es_exonerado = fields.Boolean(string='Es Exonerado', default=False,
                                 help='Indica si el producto está exonerado de impuestos')
    
    # Campos para reportes
    categoria_fiscal = fields.Selection([
        ('bienes', 'Bienes'),
        ('servicios', 'Servicios'),
        ('ambos', 'Bienes y Servicios')
    ], string='Categoría Fiscal', default='bienes')
    
    # Campos para retenciones
    aplica_retencion = fields.Boolean(string='Aplica Retención', default=False)
    porcentaje_retencion = fields.Float(string='Porcentaje de Retención', default=0.0)
    tipo_servicio_retencion = fields.Selection([
        ('transporte_carga', 'Transporte de Carga'),
        ('alquiler_local', 'Alquiler de Locales'),
        ('alquiler_maquinaria', 'Alquiler de Maquinaria/Equipo'),
        ('seguridad', 'Servicios de Seguridad'),
        ('limpieza', 'Servicios de Limpieza'),
        ('mantenimiento', 'Mantenimiento de Equipo'),
        ('otros_servicios', 'Otros Servicios'),
    ], string='Tipo Servicio Retención',
       help='Tipo de servicio según Acuerdo DEI-215-2010 '
            'para el libro de retenciones SAR.',
    )

    aplica_retencion_isr = fields.Boolean(
        string='Aplica Retención ISR',
        default=False,
        help='Si está marcado, se aplica retención ISR '
             'automáticamente cuando el proveedor NO tiene '
             'Constancia de Pago a Cuenta SAR vigente.',
    )
    impuesto_retencion_isr_id = fields.Many2one(
        'account.tax',
        string='Impuesto de Retención ISR',
        domain="[('is_retention','=',True),"
               "('type_tax_use','=','purchase'),"
               "('tipo_impuesto','=','retencion')]",
        help='Impuesto de retención ISR específico para '
             'honorarios (12.5%), anticipo bienes (1%) '
             'o alquiler habitacional (10%).',
    )

    # ── Régimen de Zona Libre (ZOLI) ──────────────────────────
    requiere_control_duca = fields.Boolean(
        string='Requiere control DUCA (MP importada)',
        default=False,
        help='Marca este producto como materia prima importada bajo régimen '
             'de Zona Libre (ej. Resinas/PVC). En compañías ZOLI, su recepción '
             'exige el número DUCA y el documento adjunto, y queda sujeta al '
             'control de permanencia (vencimiento).',
    )
    es_no_originario = fields.Boolean(
        string='Insumo no originario (tercer país)',
        default=True,
        help='Indica que este insumo proviene de un tercer país no cubierto '
             'por un tratado de libre comercio ratificado por Honduras. '
             'Se usa al nacionalizar productos terminados originarios para '
             'calcular el DAI sobre los insumos no originarios consumidos.',
    )
    porcentaje_dai_insumo = fields.Float(
        string='% DAI del insumo',
        default=0.0,
        help='Tasa de Derechos Arancelarios a la Importación (DAI) aplicable '
             'a este insumo según el Sistema Arancelario Centroamericano (SAC). '
             'Valores típicos: 0%, 5%, 10%, 15%.',
    )
    es_originario_tlc = fields.Boolean(
        string='Producto originario (TLC)',
        default=False,
        help='El producto terminado cumple las reglas de origen de un TLC '
             'ratificado por Honduras. Si está marcado, al nacionalizar no '
             'paga DAI sobre el bien final, sino sobre los insumos no '
             'originarios consumidos. Si no, paga DAI sobre el producto '
             'terminado según su tasa SAC.',
    )
    codigo_sac = fields.Char(
        string='Código SAC',
        help='Partida arancelaria del producto terminado en el Sistema '
             'Arancelario Centroamericano (SAC) de Honduras.',
    )
    porcentaje_dai = fields.Float(
        string='% DAI del producto',
        default=0.0,
        help='Tasa de Derechos Arancelarios a la Importación (DAI) del '
             'producto terminado según el SAC. Se aplica al nacionalizar '
             'cuando el producto NO es originario.',
    )

    @api.onchange('aplica_retencion_isr')
    def _onchange_aplica_retencion_isr(self):
        if not self.aplica_retencion_isr:
            self.impuesto_retencion_isr_id = False

    @api.constrains('requiere_control_duca', 'tracking')
    def _check_duca_tracking(self):
        for product in self:
            if product.requiere_control_duca and product.tracking != 'lot':
                raise ValidationError(_(
                    'El producto "%(nombre)s" requiere control DUCA, por lo '
                    'que debe rastrearse por lote.\n\n'
                    'Configure el seguimiento (Trazabilidad) en "Por lotes" '
                    'antes de activar el control DUCA.',
                    nombre=product.name,
                ))

    @api.constrains('aplica_retencion_isr', 'impuesto_retencion_isr_id')
    def _check_retencion_isr(self) -> None:
        for product in self:
            if (
                product.aplica_retencion_isr
                and not product.impuesto_retencion_isr_id
            ):
                raise ValidationError(_(
                    'El producto "%(nombre)s" tiene marcado '
                    '"Aplica Retención ISR" pero no tiene el '
                    'impuesto de retención configurado.\n\n'
                    'Seleccione el impuesto de retención '
                    'correspondiente.',
                    nombre=product.name,
                ))

    # ──────────────────────────────────────────────────────────
    # IMPORTANTE para desarrolladores futuros:
    # Si vas a crear/actualizar productos desde un cron, hook,
    # wizard o importación masiva donde la categoría no pueda ser
    # revisada por el usuario en el momento, usa:
    #
    #   self.with_context(skip_categ_check=True).create(vals_list)
    #
    # De lo contrario el constraint de validación contable de
    # categoría se aplicará igual.
    # ──────────────────────────────────────────────────────────
    # Campos cuya escritura suele venir de procesos automáticos (valuación de
    # inventario, mensajería) y NO debe disparar la validación de categoría,
    # para no romper flujos del sistema.
    _CATEG_CHECK_AUTO_FIELDS = {
        'standard_price', 'message_main_attachment_id',
    }

    def _fiscal_categoria_validacion_error(self):
        """Mensaje de error si la categoría del producto no está validada.

        Devuelve ``False`` cuando la categoría está en estado ``'ok'``
        (técnicamente completa **y** validada por Contabilidad). En otro caso
        devuelve el texto explicando por qué no es utilizable.
        """
        self.ensure_one()
        categoria = self.categ_id.sudo()
        if not categoria:
            return False
        estado = categoria.estado_validacion_contable
        if estado == 'ok':
            return False

        if estado == 'no_valida':
            faltan = []
            if not categoria.property_account_income_categ_id:
                faltan.append(_('cuenta de ingresos'))
            if not categoria.property_account_expense_categ_id:
                faltan.append(_('cuenta de gastos'))
            if not categoria.property_cost_method:
                faltan.append(_('método de costeo'))
            if (categoria.property_valuation == 'real_time'
                    and not categoria.property_stock_journal):
                faltan.append(_('diario de stock'))
            return _(
                "El producto '%(prod)s' tiene la categoría '%(cat)s' sin la "
                "configuración contable mínima para la compañía '%(comp)s'.\n"
                "Falta configurar: %(faltan)s.",
                prod=self.display_name,
                cat=categoria.display_name,
                comp=self.env.company.display_name,
                faltan=', '.join(faltan),
            )

        # estado == 'pendiente': configuración técnica completa pero sin la
        # validación humana de Contabilidad.
        return _(
            "El producto '%(prod)s' tiene la categoría '%(cat)s' que aún no "
            "ha sido validada por Contabilidad para la compañía '%(comp)s'.\n"
            "Pídale a Contabilidad que marque 'Validado por Contabilidad' en "
            "la categoría antes de continuar.",
            prod=self.display_name,
            cat=categoria.display_name,
            comp=self.env.company.display_name,
        )

    def _check_categoria_validacion_contable(self):
        if self.env.context.get('skip_categ_check'):
            return
        errores = [
            error for error in (
                producto._fiscal_categoria_validacion_error()
                for producto in self
            ) if error
        ]
        if errores:
            raise ValidationError(
                _("No se puede guardar el producto.\n\n")
                + "\n\n".join(errores)
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Validación dura SIEMPRE en create (categ_id siempre tiene valor).
        records._check_categoria_validacion_contable()
        return records

    def write(self, vals):
        res = super().write(vals)
        # Validar al guardar/modificar el producto, salvo escrituras puramente
        # automáticas (p. ej. valuación de inventario) o con skip explícito.
        if (not self.env.context.get('skip_categ_check')
                and set(vals.keys()) - self._CATEG_CHECK_AUTO_FIELDS):
            self._check_categoria_validacion_contable()
        return res

    @api.onchange("exento")
    def _set_taxes_id(self):
        for r in self:
            if r.exento == True:
                r.taxes_id = False

    @api.onchange('es_exento', 'es_exonerado')
    def _onchange_exemption_status(self):
        """Actualiza automáticamente los impuestos según el estado de exención"""
        if self.es_exento:
            # Buscar grupo de impuestos exento
            exempt_tax_group = self.env['account.tax.group'].search([('name', '=', 'Exento')], limit=1)
            if exempt_tax_group:
                exempt_taxes = self.env['account.tax'].search([
                    ('tax_group_id', '=', exempt_tax_group.id),
                    ('company_id', '=', self.company_id.id)
                ])
                self.taxes_id = [(6, 0, exempt_taxes.ids)]
        
        elif self.es_exonerado:
            # Buscar grupo de impuestos exonerado
            exonerated_tax_group = self.env['account.tax.group'].search([('name', '=', 'Exonerado')], limit=1)
            if exonerated_tax_group:
                exonerated_taxes = self.env['account.tax'].search([
                    ('tax_group_id', '=', exonerated_tax_group.id),
                    ('company_id', '=', self.company_id.id)
                ])
                self.taxes_id = [(6, 0, exonerated_taxes.ids)]
        
        else:
            # Aplicar impuestos normales ISV
            isv_taxes = self.env['account.tax'].search([
                ('tipo_impuesto', '=', 'isv'),
                ('company_id', '=', self.company_id.id)
            ])
            self.taxes_id = [(6, 0, isv_taxes.ids)]


class ProductProduct(models.Model):
    _inherit = "product.product"

    # Campos del módulo original
    exento = fields.Boolean(string='Exento', readonly=False, compute='_set_exento')
    is_retention = fields.Boolean(
        string='Es Retención',
        related='product_tmpl_id.is_retention',
        readonly=False
    )
    aplica_retencion_isr = fields.Boolean(
        related='product_tmpl_id.aplica_retencion_isr',
        readonly=False,
    )
    impuesto_retencion_isr_id = fields.Many2one(
        related='product_tmpl_id.impuesto_retencion_isr_id',
        readonly=False,
    )
    requiere_control_duca = fields.Boolean(
        related='product_tmpl_id.requiere_control_duca',
        readonly=False,
        store=True,
    )
    es_no_originario = fields.Boolean(
        related='product_tmpl_id.es_no_originario',
        readonly=False,
    )
    porcentaje_dai_insumo = fields.Float(
        related='product_tmpl_id.porcentaje_dai_insumo',
        readonly=False,
    )
    es_originario_tlc = fields.Boolean(
        related='product_tmpl_id.es_originario_tlc',
        readonly=False,
    )
    codigo_sac = fields.Char(
        related='product_tmpl_id.codigo_sac',
        readonly=False,
    )
    porcentaje_dai = fields.Float(
        related='product_tmpl_id.porcentaje_dai',
        readonly=False,
    )

    @api.onchange("exento")
    def _set_taxes_id(self):
        for r in self:
            if r.exento == True:
                r.taxes_id = False

    def _set_exento(self):
        for r in self:
            r.exento = r.product_tmpl_id.exento
