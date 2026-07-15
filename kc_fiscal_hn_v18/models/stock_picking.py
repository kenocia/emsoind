# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    sequence_sar_id = fields.Many2one(
        'ir.sequence', string="Secuencia SAR Remisión",
        help="Secuencia para numerar los movimientos de este tipo."
    )


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # Campos del módulo original
    sar_name = fields.Char(
        store=True,  # Guarda el valor en la BD
        readonly=False,  # Permite edición manual si es necesario
        index=True,
    )

    cai = fields.Char(string='CAI', help='Clave de Autorización de Impresión')
    fechaLimiteEmision = fields.Datetime(string='Fecha límite de emisión',
                                         help='Fecha límite de emisión de facturas')
    numeroInicial = fields.Char(string='Número inicial',
                                help='Número inicial de facturación', )
    numeroFinal = fields.Char(string='Número final', help='Número final de facturación', )

    motivo_traslado = fields.Selection([
        ('venta', 'Venta'),
        ('importacion', 'Importación'),
        ('consignacion', 'Consignación'),
        ('devolucion', 'Devolución'),
        ('exportacion', 'Exportación'),
        ('traslado_establecimientos', 'Traslado entre establecimientos del contribuyente'),
        ('traslado_transformacion', 'Traslado de bienes para transformación'),
        ('compra', 'Compra'),
        ('rentas', 'Rentas'),
        ('traslado_reparacion', 'Traslado de bienes para reparación'),
        ('traslado_emisor_movil', 'Traslado por venta emisor móvil'),
        ('exhibicion_demostracion', 'Exhibición o demostración'),
        ('participacion_ferias', 'Participación en ferias'),
    ], string="Motivo de Traslado", help="Seleccione el motivo del traslado.")

    transporter_name = fields.Char(string="Nombre del Transportista",
                                   help="Nombre del conductor o empresa transportista")
    transporter_rtn = fields.Char(string="RTN / Identidad",
                                  help="Número de RTN o Identidad del transportista")
    vehicle_info = fields.Char(string="Marca y No. de Placa",
                               help="Marca del vehículo y número de placa")
    driver_license = fields.Char(string="Licencia de Conducir",
                                 help="Número de licencia del conductor")

    # Campos del módulo migrado
    numero_guia = fields.Char(string='Número de Guía', help='Número de guía de remisión')
    fecha_guia = fields.Date(string='Fecha de Guía', default=fields.Date.today)
    transportista = fields.Many2one('res.partner', string='Transportista', 
                                   domain=[('is_company', '=', True)])
    vehiculo = fields.Char(string='Vehículo', help='Número de placa o identificación del vehículo')
    conductor = fields.Char(string='Conductor', help='Nombre del conductor')
    
    # Campos para reportes
    tipo_transporte = fields.Selection([
        ('terrestre', 'Terrestre'),
        ('maritimo', 'Marítimo'),
        ('aereo', 'Aéreo')
    ], string='Tipo de Transporte', default='terrestre')
    
    # Campos calculados
    total_base_imponible = fields.Float(string='Total Base Imponible', 
                                       compute='_compute_totals', store=True)
    total_isv = fields.Float(string='Total ISV', 
                            compute='_compute_totals', store=True)

    def update_custom_fields(self):
        """Función para actualizar la información de numeración y CAI usando sequence_sar_id de stock.picking.type."""
        for record in self:
            picking_type = record.picking_type_id
            if not picking_type or not picking_type.sequence_sar_id:
                raise UserError(_('El tipo de operación no tiene una secuencia SAR asignada.'))

            sequence_sar = picking_type.sequence_sar_id

            if sequence_sar.use_date_range:
                date = record.scheduled_date or fields.Date.today()

                # Obtener el rango de numeración aplicable
                seq_date = self.env['ir.sequence.date_range'].search(
                    [('sequence_id', '=', sequence_sar.id),
                     ('cai_validated', '=', True),
                     ('date_from', '<=', date),
                     ('date_to', '>=', date)], limit=1)

                if not seq_date or not seq_date.cai:
                    raise UserError(
                        _('No se encontró rango de numeración o CAI configurado. '
                          'Revise que los rangos de fechas sean correctos y que la información del CAI esté ingresada.'))

                record.numeroInicial = sequence_sar.format_sequence_number(
                    seq_date.rangoInicial, date, seq_date,
                )
                record.numeroFinal = sequence_sar.format_sequence_number(
                    seq_date.rangoFinal, date, seq_date,
                )
                record.cai = seq_date.cai
                record.fechaLimiteEmision = seq_date.date_to

                # Asignar el valor de sar_name usando la secuencia
                record.sar_name = sequence_sar.next_by_id(sequence_date=record.date_done)

        return {
            'effect': {
                'fadeout': 'slow',
                'message': "Información actualizada correctamente",
                'type': 'rainbow_man',
            }
        }

    @api.depends('move_line_ids.base_imponible', 'move_line_ids.monto_isv')
    def _compute_totals(self):
        for picking in self:
            picking.total_base_imponible = sum(picking.move_line_ids.mapped('base_imponible'))
            picking.total_isv = sum(picking.move_line_ids.mapped('monto_isv'))

    def _get_motivo_traslado_label(self):
        """Etiqueta legible del motivo de traslado para reportes."""
        self.ensure_one()
        if not self.motivo_traslado:
            return ''
        selection = dict(self._fields['motivo_traslado'].selection)
        return selection.get(self.motivo_traslado, self.motivo_traslado)

    def _get_guia_remision_lines(self):
        """Líneas de producto para la guía: operaciones detalladas o movimientos."""
        self.ensure_one()
        lines = []
        move_lines = self.move_line_ids_without_package or self.move_line_ids
        if move_lines:
            sorted_lines = move_lines.sorted(
                key=lambda ml: (ml.product_id.display_name or '', ml.id),
            )
            for ml in sorted_lines:
                if not ml.product_id:
                    continue
                if self.state == 'done':
                    qty = ml.quantity
                else:
                    qty = ml.quantity or ml.product_uom_qty or ml.move_id.product_uom_qty
                lines.append({
                    'name': ml.product_id.display_name,
                    'description': ml.product_id.description_picking or '',
                    'qty': qty,
                    'uom': ml.product_uom_id.name or '',
                    'lot': ml.lot_id.name or ml.lot_name or '',
                })
        else:
            for move in self.move_ids_without_package.sorted(
                key=lambda m: (m.product_id.display_name or '', m.id),
            ):
                if not move.product_id:
                    continue
                qty = move.quantity if self.state == 'done' else move.product_uom_qty
                lines.append({
                    'name': move.product_id.display_name,
                    'description': move.product_id.description_picking or '',
                    'qty': qty,
                    'uom': move.product_uom.name or '',
                    'lot': '',
                })
        return lines

    def _get_guia_punto_partida(self):
        """Texto punto de partida (empresa + almacén)."""
        self.ensure_one()
        company = self.company_id
        parts = [company.name or '']
        warehouse = self.picking_type_id.warehouse_id
        if warehouse and warehouse.name:
            parts.append(warehouse.name)
        ubicacion = ', '.join([
            p for p in [
                company.street or '',
                company.city or '',
                company.state_id.name if company.state_id else '',
            ] if p
        ])
        if ubicacion:
            parts.append(ubicacion)
        return ' · '.join(p for p in parts if p)

    def _get_guia_punto_destino(self):
        """Texto punto de destino (cliente + dirección de entrega)."""
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return ''
        parts = [partner.display_name or partner.name or '']
        addr = partner._display_address(without_company=True)
        if addr:
            parts.append(addr.replace('\n', ', '))
        return ' · '.join(p for p in parts if p)

    def _get_salida_delivery_partner(self):
        """Dirección de entrega desde la orden de venta vinculada."""
        self.ensure_one()
        if self.sale_id and self.sale_id.partner_shipping_id:
            return self.sale_id.partner_shipping_id
        return self.partner_id

    def _get_salida_warehouse_name(self):
        """Nombre del almacén de origen de la entrega."""
        self.ensure_one()
        warehouse = self.picking_type_id.warehouse_id
        if warehouse:
            return warehouse.name
        if self.location_id.warehouse_id:
            return self.location_id.warehouse_id.name
        return self.location_id.display_name or ''

    def _get_salida_line_warehouse_name(self, move_line=None, move=None):
        """Almacén de origen para una línea del comprobante."""
        if move_line and move_line.location_id.warehouse_id:
            return move_line.location_id.warehouse_id.name
        if move_line and move_line.location_id:
            return move_line.location_id.display_name
        if move:
            if move.location_id.warehouse_id:
                return move.location_id.warehouse_id.name
            return move.location_id.display_name or ''
        return self._get_salida_warehouse_name()

    def _get_salida_inventario_line_technical_description(self, move_line=None, move=None):
        """Descripción técnica (dimensiones) para líneas del comprobante de entrega."""
        if move_line and 'lot_technical_description' in move_line._fields:
            tech = (move_line.lot_technical_description or '').strip()
            if tech:
                return tech
        sale_line = False
        lot = self.env['stock.lot']
        if move_line:
            move = move_line.move_id
            lot = move_line.lot_id
        if move:
            sale_line = move.sale_line_id
            if not lot and hasattr(move, '_kc_get_sale_lot'):
                lot = move._kc_get_sale_lot()
        tech = ''
        if lot and 'technical_description' in lot._fields:
            tech = (lot.technical_description or '').strip()
        if not tech and sale_line and 'technical_description' in sale_line._fields:
            tech = (sale_line.technical_description or '').strip()
        return tech

    def _salida_strip_product_code(self, name):
        """Quita el código interno [DEFAULT_CODE] del nombre comercial."""
        name = (name or '').strip()
        if name.startswith('['):
            end = name.find(']')
            if end > 1:
                name = name[end + 1:].strip()
        return name

    def _get_salida_inventario_lines(self):
        """Líneas detalladas para el reporte de salida de inventario."""
        self.ensure_one()
        lines = []
        move_lines = self.move_line_ids_without_package or self.move_line_ids
        if move_lines:
            sorted_lines = move_lines.sorted(
                key=lambda ml: (ml.product_id.display_name or '', ml.id),
            )
            for ml in sorted_lines:
                if not ml.product_id:
                    continue
                if self.state == 'done':
                    qty = ml.quantity
                else:
                    qty = ml.quantity or ml.product_uom_qty or ml.move_id.product_uom_qty
                lines.append({
                    'name': self._salida_strip_product_code(ml.product_id.display_name),
                    'technical_description': self._get_salida_inventario_line_technical_description(
                        move_line=ml,
                    ),
                    'lot': ml.lot_id.name or ml.lot_name or '',
                    'qty': qty,
                    'uom': ml.product_uom_id.name or '',
                    'warehouse': self._get_salida_line_warehouse_name(move_line=ml),
                })
        else:
            for move in self.move_ids_without_package.sorted(
                key=lambda m: (m.product_id.display_name or '', m.id),
            ):
                if not move.product_id:
                    continue
                qty = move.quantity if self.state == 'done' else move.product_uom_qty
                lines.append({
                    'name': self._salida_strip_product_code(move.product_id.display_name),
                    'technical_description': self._get_salida_inventario_line_technical_description(
                        move=move,
                    ),
                    'lot': '',
                    'qty': qty,
                    'uom': move.product_uom.name or '',
                    'warehouse': self._get_salida_line_warehouse_name(move=move),
                })
        return lines

    def _get_salida_pending_backorder_lines(self):
        """Cantidades pendientes en backorders abiertos."""
        self.ensure_one()
        lines = []
        pending = self.backorder_ids.filtered(
            lambda p: p.state not in ('done', 'cancel'),
        )
        for backorder in pending:
            for move in backorder.move_ids_without_package.filtered(
                lambda m: m.product_uom_qty > 0,
            ):
                lines.append({
                    'name': self._salida_strip_product_code(move.product_id.display_name),
                    'technical_description': self._get_salida_inventario_line_technical_description(
                        move=move,
                    ),
                    'qty': move.product_uom_qty,
                    'uom': move.product_uom.name or '',
                })
        return lines

    def action_print_salida_inventario(self):
        """Imprime el reporte de salida de inventario (entregas a clientes)."""
        report = self.env.ref(
            'kc_fiscal_hn_v18.report_salida_inventario',
            raise_if_not_found=False,
        )
        if not report:
            raise UserError(_(
                'El reporte de Comprobante de entrega no está disponible. '
                'Actualice el módulo kc_fiscal_hn_v18.'
            ))
        self.write({'printed': True})
        return report.report_action(self, config=False)

    def do_print_picking(self):
        outgoing = self.filtered(lambda p: p.picking_type_code == 'outgoing')
        if outgoing:
            return outgoing.action_print_salida_inventario()
        return super().do_print_picking()

    # ── Control de Zona Libre (ZOLI / DUCA) ───────────────────
    def _duca_lineas_control(self):
        """Líneas de movimiento de productos sujetos a control DUCA."""
        self.ensure_one()
        return self.move_line_ids.filtered(
            lambda ml: ml.product_id.requiere_control_duca
        )

    def _validar_recepcion_duca(self):
        """Exige N° DUCA y documento en recepciones de MP importada (ZOLI)."""
        self.ensure_one()
        if not self.company_id.es_zoli:
            return
        if self.picking_type_code != 'incoming':
            return
        faltantes = []
        for ml in self._duca_lineas_control():
            lot = ml.lot_id
            if not lot:
                faltantes.append(_(
                    '- %(prod)s: falta el lote/DUCA',
                    prod=ml.product_id.display_name,
                ))
                continue
            errores_lote = []
            if not lot.duca_number:
                errores_lote.append(_('número DUCA'))
            if not lot.duca_documento:
                errores_lote.append(_('documento DUCA adjunto'))
            if errores_lote:
                faltantes.append(_(
                    '- %(prod)s (lote %(lote)s): falta %(faltan)s',
                    prod=ml.product_id.display_name,
                    lote=lot.name,
                    faltan=', '.join(errores_lote),
                ))
            if lot and not lot.duca_fecha_ingreso:
                lot.duca_fecha_ingreso = (
                    self.date_done or fields.Date.context_today(self)
                )
        if faltantes:
            raise UserError(_(
                'No es posible validar la recepción de materia prima '
                'importada bajo régimen de Zona Libre.\n\n'
                'Complete la información DUCA de cada lote:\n\n%(faltan)s',
                faltan='\n'.join(faltantes),
            ))

    def _validar_salida_duca(self):
        """Bloquea la salida/consumo de lotes DUCA vencidos (ZOLI)."""
        self.ensure_one()
        if not self.company_id.es_zoli:
            return
        if self.picking_type_code not in ('outgoing', 'internal'):
            return
        lots = self._duca_lineas_control().mapped('lot_id')
        if lots:
            lots._check_duca_no_vencido(document=self)

    def button_validate(self):
        for picking in self:
            picking._validar_salida_duca()
        result = super().button_validate()
        for picking in self:
            if picking.state == 'done':
                picking._validar_recepcion_duca()
        return result