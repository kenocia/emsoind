# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import _, api, fields, models


class ManualUsoFiscalHN(models.TransientModel):
    _name = 'kc_fiscal_hn.manual.uso'
    _description = 'Manual de Uso Fiscal Honduras'

    seccion_activa = fields.Selection([
        ('bienvenida', 'Bienvenida'),
        ('configuracion', 'Configuración Inicial'),
        ('usuarios', 'Usuarios y Contador'),
        ('contactos', 'Contactos y RTN'),
        ('diarios', 'Diarios Contables'),
        ('impuestos', 'Impuestos SAR'),
        ('secuencias', 'Secuencias y CAI'),
        ('productos', 'Productos y Retenciones'),
        ('facturas_venta', 'Facturas de Venta'),
        ('facturas_compra', 'Facturas de Compra'),
        ('guias_remision', 'Guías de Remisión'),
        ('retenciones', 'Retenciones ISR'),
        ('exoneracion', 'Exoneración'),
        ('consumidor_final', 'Consumidor Final'),
        ('zoli', 'Zona Libre (ZOLI)'),
        ('libros_sar', 'Libros SAR'),
        ('dashboard', 'Dashboard Fiscal'),
        ('informes', 'Informes Excel'),
        ('importacion', 'Importación de Datos'),
        ('cierre', 'Cierre Mensual'),
        ('implementador', 'Guía Implementador'),
    ], default='bienvenida', string='Sección')

    # Perfil de empresa: adapta el contenido del manual en vivo.
    perfil_empresa = fields.Selection([
        ('pequeno', 'Pequeño Contribuyente'),
        ('mediano', 'Mediano Contribuyente'),
        ('grande', 'Grande Contribuyente'),
    ], string='Tipo de empresa', default='pequeno')
    es_zoli_manual = fields.Boolean(string='Empresa Zona Libre (ZOLI)')
    tipo_confirmado = fields.Boolean(
        string='Tipo de empresa confirmado',
        default=False,
        help='Hasta confirmar el tipo de empresa no se muestra el contenido '
             'del manual; al confirmar, el manual se adapta a ese perfil.',
    )
    solo_aplicables = fields.Boolean(
        string='Mostrar solo lo que aplica',
        default=True,
        help='Oculta las secciones y opciones que no aplican al tipo de '
             'empresa seleccionado (DMC para no obligados, ZOLI si no es Zona '
             'Libre). Desactívalo para ver todo el manual.',
    )

    # ── Diagnóstico de configuración (en vivo, según la empresa) ──
    config_estado = fields.Selection([
        ('ok', 'Completa'),
        ('warning', 'Con advertencias'),
        ('error', 'Incompleta'),
    ], string='Estado de configuración',
       compute='_compute_config_diagnostico')
    config_pendientes_count = fields.Integer(
        string='Pendientes de configurar',
        compute='_compute_config_diagnostico',
    )
    config_diagnostico_html = fields.Html(
        string='Diagnóstico de configuración',
        compute='_compute_config_diagnostico',
        sanitize=False,
    )

    @api.depends('perfil_empresa', 'es_zoli_manual')
    def _compute_config_diagnostico(self):
        for manual in self:
            checks = manual._build_config_checks(self.env.company)
            pendientes = [c for c in checks if c['nivel'] in ('error', 'warning')]
            manual.config_pendientes_count = len(pendientes)
            if any(c['nivel'] == 'error' for c in checks):
                manual.config_estado = 'error'
            elif any(c['nivel'] == 'warning' for c in checks):
                manual.config_estado = 'warning'
            else:
                manual.config_estado = 'ok'
            manual.config_diagnostico_html = manual._render_config_html(checks)

    def _build_config_checks(self, company):
        """Devuelve la lista de verificaciones de configuración de la empresa.

        Cada elemento: {'nivel': ok|warning|error, 'titulo', 'detalle'}.
        Lee datos reales de la compañía y de los registros del módulo para que
        el manual refleje cómo está configurada la empresa.
        """
        self.ensure_one()
        Tax = self.env['account.tax']
        Seq = self.env['ir.sequence']
        Journal = self.env['account.journal']
        CodigoSAR = self.env['kc_fiscal_hn.codigo.sar']
        checks = []

        # 1) RTN de la empresa (campo nativo de Odoo: vat)
        rtn = ''.join(ch for ch in (company.vat or '') if ch.isdigit())
        if len(rtn) in (13, 14):
            checks.append({
                'nivel': 'ok',
                'titulo': 'RTN de la empresa',
                'detalle': 'RTN %s configurado.' % rtn,
            })
        else:
            checks.append({
                'nivel': 'error',
                'titulo': 'RTN de la empresa',
                'detalle': 'Falta el RTN o no tiene 13/14 dígitos. Se captura '
                           'en el campo "RTN" de la empresa '
                           '(Ajustes → Compañías → Información general).',
            })

        # 2) Resolución SAR
        if company.fiscal_resolution and company.fiscal_resolution_date:
            checks.append({
                'nivel': 'ok',
                'titulo': 'Resolución SAR',
                'detalle': 'Resolución %s vigente.' % company.fiscal_resolution,
            })
        else:
            checks.append({
                'nivel': 'warning',
                'titulo': 'Resolución SAR',
                'detalle': 'Falta el número y/o la fecha de la resolución SAR '
                           '(necesaria para el pie de las facturas).',
            })

        # 3) Tipo de contribuyente
        tipo_label = dict(
            company._fields['tipo_contribuyente'].selection,
        ).get(company.tipo_contribuyente, '—')
        checks.append({
            'nivel': 'ok',
            'titulo': 'Tipo de contribuyente',
            'detalle': '%s%s.' % (
                tipo_label,
                ' · obligado a DMC' if company.obligado_dmc else '',
            ),
        })

        # 4) Códigos SAR cargados
        codigos = CodigoSAR.search_count([('activo', '=', True)])
        if codigos:
            checks.append({
                'nivel': 'ok',
                'titulo': 'Códigos SAR',
                'detalle': '%d códigos SAR activos.' % codigos,
            })
        else:
            checks.append({
                'nivel': 'error',
                'titulo': 'Códigos SAR',
                'detalle': 'No hay códigos SAR cargados. Fiscal HN → '
                           'Configuraciones → Códigos SAR.',
            })

        # 5) Impuestos vinculados a código SAR
        isv_venta = Tax.search_count([
            ('type_tax_use', '=', 'sale'),
            ('codigo_sar_id', '!=', False),
            ('tipo_impuesto', '=', 'isv'),
        ])
        isv_compra = Tax.search_count([
            ('type_tax_use', '=', 'purchase'),
            ('codigo_sar_id', '!=', False),
            ('tipo_impuesto', '=', 'isv'),
        ])
        if not isv_venta:
            checks.append({
                'nivel': 'error',
                'titulo': 'Impuestos ISV con Código SAR',
                'detalle': 'Ningún ISV de ventas tiene Código SAR asignado. '
                           'Los Libros SAR no clasificarán las ventas.',
            })
        elif not isv_compra:
            checks.append({
                'nivel': 'warning',
                'titulo': 'Impuestos ISV con Código SAR',
                'detalle': 'ISV de ventas OK, pero falta vincular el ISV de '
                           'compras (crédito fiscal DMC).',
            })
        else:
            checks.append({
                'nivel': 'ok',
                'titulo': 'Impuestos ISV con Código SAR',
                'detalle': 'ISV de ventas y compras vinculados al SAR.',
            })

        # 6) Secuencias fiscales (CAI)
        seq_fiscales = Seq.search_count([
            ('is_fiscal', '=', True),
            ('company_id', 'in', [company.id, False]),
        ])
        if seq_fiscales:
            checks.append({
                'nivel': 'ok',
                'titulo': 'Secuencias fiscales (CAI)',
                'detalle': '%d secuencia(s) fiscal(es) creada(s).' % seq_fiscales,
            })
        else:
            checks.append({
                'nivel': 'error',
                'titulo': 'Secuencias fiscales (CAI)',
                'detalle': 'No hay secuencias fiscales con CAI. Fiscal HN → '
                           'Secuencias Fiscales / Pre-registro CAI.',
            })

        # 7) Diarios con documento fiscal
        diarios_fiscales = Journal.search_count([
            ('company_id', '=', company.id),
            ('document_fiscal', '!=', False),
        ])
        diarios_incompletos = Journal.search_count([
            ('company_id', '=', company.id),
            ('document_fiscal', '!=', False),
            ('fiscal_config_state', '!=', 'ok'),
        ])
        if not diarios_fiscales:
            checks.append({
                'nivel': 'warning',
                'titulo': 'Diarios fiscales',
                'detalle': 'Ningún diario está marcado como Documento Fiscal.',
            })
        elif diarios_incompletos:
            checks.append({
                'nivel': 'warning',
                'titulo': 'Diarios fiscales',
                'detalle': '%d diario(s) fiscal(es) con configuración '
                           'incompleta o CAI en alerta/vencido.'
                           % diarios_incompletos,
            })
        else:
            checks.append({
                'nivel': 'ok',
                'titulo': 'Diarios fiscales',
                'detalle': '%d diario(s) fiscal(es) operativo(s).'
                           % diarios_fiscales,
            })

        # 8) Consumidor Final
        if company.consumidor_final_control_activo:
            if not company.consumidor_final_partner_id:
                checks.append({
                    'nivel': 'warning',
                    'titulo': 'Consumidor Final',
                    'detalle': 'Control activo pero falta el contacto '
                               'Consumidor Final en la compañía.',
                })
            elif not company.consumidor_final_monto_maximo:
                checks.append({
                    'nivel': 'warning',
                    'titulo': 'Consumidor Final',
                    'detalle': 'Falta definir el monto máximo (0 = sin límite).',
                })
            else:
                checks.append({
                    'nivel': 'ok',
                    'titulo': 'Consumidor Final',
                    'detalle': 'Contacto y monto máximo configurados.',
                })
        else:
            checks.append({
                'nivel': 'ok',
                'titulo': 'Consumidor Final',
                'detalle': 'Control de monto desactivado (opcional).',
            })

        # 9) Zona Libre (solo si la empresa es ZOLI)
        if company.es_zoli:
            falta_zoli = []
            if not company.duca_responsable_compras_id:
                falta_zoli.append('responsable de compras')
            if not company.duca_responsable_bodega_id:
                falta_zoli.append('responsable de bodega')
            if not company.zoli_limite_local_pct:
                falta_zoli.append('límite de ventas locales (%)')
            if falta_zoli:
                checks.append({
                    'nivel': 'warning',
                    'titulo': 'Zona Libre (ZOLI)',
                    'detalle': 'Falta configurar: %s.' % ', '.join(falta_zoli),
                })
            else:
                checks.append({
                    'nivel': 'ok',
                    'titulo': 'Zona Libre (ZOLI)',
                    'detalle': 'Permanencia DUCA, responsables y límite '
                               'configurados.',
                })

        return checks

    def _render_config_html(self, checks):
        estilos = {
            'ok': ('list-group-item-success', '✅'),
            'warning': ('list-group-item-warning', '⚠️'),
            'error': ('list-group-item-danger', '⛔'),
        }
        filas = []
        for chk in checks:
            cls, icono = estilos.get(chk['nivel'], ('', 'ℹ️'))
            filas.append(Markup(
                '<div class="list-group-item %s py-2">'
                '<strong>%s %s</strong><br/>'
                '<small>%s</small></div>'
            ) % (cls, icono, chk['titulo'], chk['detalle']))
        cuerpo = Markup('').join(filas)
        return Markup(
            '<div class="list-group small">%s</div>'
        ) % cuerpo

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        res.setdefault('perfil_empresa', company.tipo_contribuyente or 'pequeno')
        res.setdefault('es_zoli_manual', company.es_zoli)
        return res

    @api.depends('seccion_activa')
    def _compute_display_name(self):
        for manual in self:
            manual.display_name = _('Manual de Uso Fiscal Honduras')

    @api.model
    def action_open_manual(self):
        """Abre el manual interactivo reutilizando un único registro/usuario.

        Evita crear un registro transitorio nuevo (id incremental) cada vez
        que se abre el manual desde el menú.
        """
        company = self.env.company
        manuales = self.search(
            [('create_uid', '=', self.env.user.id)], order='id desc',
        )
        manual = manuales[:1]
        if manuales - manual:
            (manuales - manual).unlink()
        if not manual:
            manual = self.create({})
        manual.write({
            'seccion_activa': 'bienvenida',
            'perfil_empresa': company.tipo_contribuyente or 'pequeno',
            'es_zoli_manual': company.es_zoli,
            'tipo_confirmado': False,
        })
        return manual._reopen()

    def action_confirmar_tipo(self):
        """Confirma el tipo de empresa y habilita el contenido del manual."""
        self.ensure_one()
        self.write({
            'tipo_confirmado': True,
            'seccion_activa': 'bienvenida',
        })
        return self._reopen()

    def action_cambiar_tipo(self):
        """Vuelve al selector de tipo de empresa (oculta el contenido)."""
        self.ensure_one()
        self.tipo_confirmado = False
        return self._reopen()

    # ── Accesos directos a las pantallas de configuración ──────
    def _abrir_accion(self, xmlid):
        self.ensure_one()
        try:
            return self.env['ir.actions.act_window']._for_xml_id(xmlid)
        except ValueError:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Acción no disponible'),
                    'message': _(
                        'No se encontró la pantalla solicitada (%s).'
                    ) % xmlid,
                    'type': 'warning',
                },
            }

    def action_abrir_compania(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Compañía'),
            'res_model': 'res.company',
            'res_id': self.env.company.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_abrir_usuarios(self):
        return self._abrir_accion('base.action_res_users')

    def action_abrir_grupos(self):
        return self._abrir_accion('base.action_res_groups')

    def action_abrir_contactos(self):
        return self._abrir_accion('base.action_partner_form')

    def action_abrir_diarios(self):
        return self._abrir_accion('kc_fiscal_hn_v18.action_fiscal_journals')

    def action_abrir_codigos(self):
        return self._abrir_accion('kc_fiscal_hn_v18.action_codigo_sar')

    def action_abrir_impuestos(self):
        return self._abrir_accion('kc_fiscal_hn_v18.action_impuestos_sar')

    def action_abrir_secuencias(self):
        return self._abrir_accion('kc_fiscal_hn_v18.action_fiscal_sequences')

    def action_abrir_preregistro(self):
        return self._abrir_accion('kc_fiscal_hn_v18.action_preregistro_cai')

    def action_abrir_productos(self):
        return self._abrir_accion('product.product_template_action')

    def action_abrir_categorias(self):
        return self._abrir_accion('product.product_category_action_form')

    def action_abrir_guias(self):
        return self._abrir_accion('stock.action_picking_tree_all')

    def action_abrir_libro_ventas(self):
        return self._abrir_accion('kc_fiscal_hn_v18.action_book_sales')

    def action_abrir_libro_compras(self):
        return self._abrir_accion('kc_fiscal_hn_v18.action_book_purchases')

    def action_abrir_libro_retenciones(self):
        return self._abrir_accion('kc_fiscal_hn_v18.action_book_retentions')

    def action_abrir_bloqueos_cf(self):
        return self._abrir_accion('kc_fiscal_hn_v18.action_consumidor_final_audit')

    def action_abrir_duca_activos(self):
        return self._abrir_accion('kc_fiscal_hn_v18.action_zoli_duca_activos')

    def action_abrir_salud_fiscal(self):
        return self._abrir_accion('kc_fiscal_hn_v18.action_salud_fiscal')

    def _go_section(self, section_key):
        self.ensure_one()
        self.seccion_activa = section_key
        return self._reopen()

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manual de Uso Fiscal Honduras'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'view_id': self.env.ref(
                'kc_fiscal_hn_v18.view_manual_uso_fiscal_hn',
            ).id,
            'context': {
                **self.env.context,
                'create': False,
                'delete': False,
            },
        }

    def action_ir_bienvenida(self):
        return self._go_section('bienvenida')

    def action_ir_configuracion(self):
        return self._go_section('configuracion')

    def action_ir_usuarios(self):
        return self._go_section('usuarios')

    def action_ir_contactos(self):
        return self._go_section('contactos')

    def action_ir_diarios(self):
        return self._go_section('diarios')

    def action_ir_impuestos(self):
        return self._go_section('impuestos')

    def action_ir_secuencias(self):
        return self._go_section('secuencias')

    def action_ir_productos(self):
        return self._go_section('productos')

    def action_ir_facturas_venta(self):
        return self._go_section('facturas_venta')

    def action_ir_facturas_compra(self):
        return self._go_section('facturas_compra')

    def action_ir_guias_remision(self):
        return self._go_section('guias_remision')

    def action_ir_retenciones(self):
        return self._go_section('retenciones')

    def action_ir_exoneracion(self):
        return self._go_section('exoneracion')

    def action_ir_consumidor_final(self):
        return self._go_section('consumidor_final')

    def action_ir_zoli(self):
        return self._go_section('zoli')

    def action_ir_libros_sar(self):
        return self._go_section('libros_sar')

    def action_ir_dashboard(self):
        return self._go_section('dashboard')

    def action_ir_informes(self):
        return self._go_section('informes')

    def action_ir_importacion(self):
        return self._go_section('importacion')

    def action_ir_cierre(self):
        return self._go_section('cierre')

    def action_ir_implementador(self):
        return self._go_section('implementador')
