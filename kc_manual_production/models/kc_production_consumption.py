# -*- coding: utf-8 -*-
from datetime import datetime, time

from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError, ValidationError


class KcProductionConsumption(models.Model):
    """Consumo de Materia Prima (CMP).

    Representa la SALIDA de Materia Prima del inventario (valorizada al costo por
    Odoo en el stock.move) hacia la ubicación virtual de Producción. Puede
    vincularse opcionalmente a un Registro de Producción y/o a una Orden de Venta.
    """
    _name = 'kc.production.consumption'
    _description = 'Consumo de Materia Prima Manual'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'analytic.mixin']
    _order = 'date_consumption desc, id desc'

    name = fields.Char(
        string='Referencia',
        default='/',
        readonly=True,
        copy=False,
        index=True,
        help="Se asigna automáticamente desde la secuencia al confirmar el consumo.",
    )
    entry_id = fields.Many2one(
        comodel_name='kc.production.entry',
        string='Registro de Producción',
        domain="[('id', 'in', available_entry_ids)]",
        help="Registro de Producción (RP) opcional al que se asocia este consumo. "
             "Solo se listan los RP cuyo consumo aún no fue marcado como completo.",
    )
    available_entry_ids = fields.Many2many(
        comodel_name='kc.production.entry',
        string='RP disponibles',
        compute='_compute_available_entry_ids',
        help="Registros de Producción confirmados/validados cuyo consumo aún no "
             "está cerrado (no marcado como completo).",
    )
    consumption_completeness = fields.Selection(
        selection=[
            ('parcial', 'Parcial'),
            ('completo', 'Completo'),
        ],
        string='Tipo de Consumo',
        default='completo',
        required=True,
        help="PARCIAL: el Registro de Producción sigue disponible para registrar "
             "más consumos.\n"
             "COMPLETO: cierra el consumo del RP, que dejará de aparecer para "
             "nuevos consumos.",
    )
    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Orden de Venta',
        domain="[('state', 'in', ['sale', 'done'])]",
        help="Orden de Venta opcional, independiente de si hay RP vinculado.",
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Cliente',
        related='sale_order_id.partner_id',
        store=True,
        readonly=False,
        help="Se hereda de la Orden de Venta; editable manualmente.",
    )
    date_consumption = fields.Datetime(
        string='Fecha de Consumo',
        default=fields.Datetime.now,
        required=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('confirmed', 'Confirmado'),
            ('done', 'Validado'),
            ('cancel', 'Cancelado'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    line_ids = fields.One2many(
        comodel_name='kc.production.consumption.line',
        inverse_name='consumption_id',
        string='Líneas de Materia Prima',
        copy=True,
    )
    picking_id = fields.Many2one(
        comodel_name='stock.picking',
        string='Albarán de Salida',
        readonly=True,
        copy=False,
        help="Movimiento de inventario generado al validar el consumo.",
    )
    kc_service_move_ids = fields.Many2many(
        comodel_name='account.move',
        relation='kc_consumption_service_move_rel',
        column1='consumption_id',
        column2='move_id',
        string='Asientos de Servicio',
        readonly=True,
        copy=False,
        help="Asientos contables generados para las líneas de servicio "
             "(no mueven inventario).",
    )
    notes = fields.Text(string='Notas')
    move_line_count = fields.Integer(
        string='N° Movimientos',
        compute='_compute_move_line_count',
    )
    account_move_count = fields.Integer(
        string='N° Asientos',
        compute='_compute_account_move_count',
    )
    # analytic_distribution proviene del analytic.mixin pero aquí lo dejamos como
    # campo EDITABLE puro (compute=False): la propuesta por defecto se gestiona
    # con onchange para poder "seguir" a la fuente (RP/OV) hasta que el gerente
    # haga un reparto manual (p. ej. mermas a centros de costo 60%/40%).
    analytic_distribution = fields.Json(
        string='Distribución Analítica',
        compute=False,
        store=True,
        copy=True,
        help="Por defecto se hereda del RP/Orden de Venta. Editable para cargar "
             "el consumo a uno o varios centros de costo (reparto porcentual).",
    )
    kc_analytic_inherited = fields.Json(
        string='Analítica Heredada (memoria)',
        copy=False,
        help="Último valor analítico propuesto por herencia. Uso interno: permite "
             "re-proponer al cambiar la fuente sin pisar un reparto manual.",
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    consumption_mode = fields.Selection(
        selection=[
            ('daily', 'Consumo diario'),
            ('supply', 'Abastecimiento'),
            ('legacy', 'General'),
        ],
        string='Modo de consumo',
        default='legacy',
        required=True,
        tracking=True,
        help="DIARIO: cierre operativo por línea y fecha.\n"
             "ABASTECIMIENTO: generado desde solicitud de compra.\n"
             "GENERAL: consumo libre o vinculado a un RP.",
    )
    consumption_date = fields.Date(
        string='Fecha del período',
        index=True,
        help="Día operativo que cierra este consumo (obligatorio en modo diario).",
    )
    production_line_id = fields.Many2one(
        comodel_name='kc.production.line',
        string='Línea de Producción',
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
        index=True,
        help="Línea responsable del consumo diario.",
    )
    work_center_id = fields.Many2one(
        comodel_name='kc.work.center',
        string='Centro de Trabajo',
        domain="[('production_line_id', '=', production_line_id), "
               "('state', '=', 'active'), ('active', '=', True)]",
        help="Centro opcional asociado al consumo.",
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Bodega',
        default=lambda self: self._default_warehouse_id(),
        domain="[('company_id', '=', company_id)]",
        required=True,
        help="Almacén de origen desde donde sale la Materia Prima.",
    )
    picking_type_id = fields.Many2one(
        comodel_name='stock.picking.type',
        string='Tipo de Operación',
        compute='_compute_picking_type_id',
        readonly=True,
        help="Tipo de operación de Consumo de MP (CMP) usado al validar.",
    )
    location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Ubicación de Bodega MP',
        compute='_compute_location_id',
        help="Ubicación de origen desde donde sale la Materia Prima "
             "(según el tipo de operación CMP).",
    )

    # ---- Campos de reversión (corrección tipo "nota de crédito") ----------
    reversal_of_id = fields.Many2one(
        comodel_name='kc.production.consumption',
        string='Reversión de',
        readonly=True,
        copy=False,
        help="Consumo original que este documento revierte.",
    )
    reversed_by_id = fields.Many2one(
        comodel_name='kc.production.consumption',
        string='Revertido por',
        compute='_compute_reversed_by_id',
        help="Consumo de reversión que anula el efecto de este documento.",
    )
    is_reversal = fields.Boolean(
        string='Es Reversión',
        compute='_compute_is_reversal',
    )
    notes_reversal = fields.Text(
        string='Motivo de la Reversión',
        readonly=True,
        copy=False,
    )

    @api.constrains(
        'consumption_mode', 'production_line_id', 'consumption_date',
        'company_id', 'state',
    )
    def _check_daily_cmp_unique(self):
        for rec in self:
            if rec.consumption_mode != 'daily' or rec.state == 'cancel':
                continue
            dup = self.search([
                ('id', '!=', rec.id),
                ('consumption_mode', '=', 'daily'),
                ('production_line_id', '=', rec.production_line_id.id),
                ('consumption_date', '=', rec.consumption_date),
                ('company_id', '=', rec.company_id.id),
                ('state', '!=', 'cancel'),
            ], limit=1)
            if dup:
                raise ValidationError(_(
                    'Ya existe un consumo diario para %(line)s en %(date)s: %(cmp)s.',
                    line=rec.production_line_id.display_name,
                    date=fields.Date.to_string(rec.consumption_date),
                    cmp=dup.display_name,
                ))

    @api.model
    def _default_warehouse_id(self):
        """Primer almacén de la compañía activa como bodega por defecto."""
        return self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)

    @api.constrains('consumption_mode', 'production_line_id', 'consumption_date', 'company_id')
    def _check_daily_cmp_required_fields(self):
        for rec in self:
            if rec.consumption_mode != 'daily' or rec.state == 'cancel':
                continue
            if not rec.production_line_id:
                raise ValidationError(_(
                    'El consumo diario debe indicar la línea de producción.'))
            if not rec.consumption_date:
                raise ValidationError(_(
                    'El consumo diario debe indicar la fecha del período.'))
            if rec.production_line_id.company_id != rec.company_id:
                raise ValidationError(_(
                    'La línea de producción debe pertenecer a la misma compañía.'))

    @api.model
    def _kc_daily_open_states(self):
        return ['draft', 'confirmed']

    def _kc_get_effective_production_line(self):
        self.ensure_one()
        return self.production_line_id or (
            self.entry_id.production_line_id if self.entry_id else False
        )

    @api.model
    def _kc_find_blocking_daily_cmp(self, line, consumption_date, company=None):
        """CMP diario abierto con fecha anterior que bloquea un nuevo día."""
        if not line or not consumption_date:
            return self.browse()
        company = company or line.company_id or self.env.company
        return self.search([
            ('consumption_mode', '=', 'daily'),
            ('production_line_id', '=', line.id),
            ('company_id', '=', company.id),
            ('consumption_date', '<', consumption_date),
            ('state', 'in', self._kc_daily_open_states()),
        ], order='consumption_date desc', limit=1)

    @api.model
    def _kc_find_daily_cmp(self, line, consumption_date, company=None, states=None):
        if not line or not consumption_date:
            return self.browse()
        company = company or line.company_id or self.env.company
        domain = [
            ('consumption_mode', '=', 'daily'),
            ('production_line_id', '=', line.id),
            ('company_id', '=', company.id),
            ('consumption_date', '=', consumption_date),
        ]
        if states is not None:
            domain.append(('state', 'in', states))
        else:
            domain.append(('state', '!=', 'cancel'))
        return self.search(domain, limit=1)

    @api.model
    def _kc_prepare_daily_vals(self, vals):
        vals.setdefault('consumption_mode', 'daily')
        vals.setdefault('consumption_date', fields.Date.context_today(self))
        if vals.get('consumption_date') and not vals.get('date_consumption'):
            day = fields.Date.from_string(vals['consumption_date'])
            vals['date_consumption'] = datetime.combine(day, time(12, 0, 0))

    @api.model
    def _kc_assert_daily_can_create(self, line, consumption_date, company=None):
        company = company or self.env.company
        existing = self._kc_find_daily_cmp(line, consumption_date, company=company)
        if existing:
            raise UserError(_(
                'Ya existe un consumo diario para %(line)s en la fecha %(date)s: %(cmp)s.',
                line=line.display_name,
                date=fields.Date.to_string(consumption_date),
                cmp=existing.display_name,
            ))
        blocking = self._kc_find_blocking_daily_cmp(line, consumption_date, company=company)
        if blocking:
            raise UserError(_(
                'No puede crear el consumo del %(target)s para %(line)s. '
                'Primero valide o cancele %(cmp)s del %(date)s.',
                target=fields.Date.to_string(consumption_date),
                line=line.display_name,
                cmp=blocking.display_name,
                date=fields.Date.to_string(blocking.consumption_date),
            ))

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            if vals.get('consumption_mode') == 'daily':
                self._kc_prepare_daily_vals(vals)
                line = self.env['kc.production.line'].browse(
                    vals.get('production_line_id'))
                cdate = vals.get('consumption_date')
                if line and cdate:
                    self._kc_assert_daily_can_create(
                        line,
                        fields.Date.from_string(cdate)
                        if isinstance(cdate, str) else cdate,
                        company=self.env['res.company'].browse(vals.get('company_id'))
                        if vals.get('company_id') else self.env.company,
                    )
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        if any(f in vals for f in ('consumption_mode', 'production_line_id', 'consumption_date', 'state')):
            for rec in self:
                mode = vals.get('consumption_mode', rec.consumption_mode)
                if mode != 'daily' and rec.consumption_mode != 'daily':
                    continue
                line_id = vals.get('production_line_id', rec.production_line_id.id)
                cdate = vals.get('consumption_date', rec.consumption_date)
                line = self.env['kc.production.line'].browse(line_id) if line_id else False
                if line and cdate and rec.state != 'cancel':
                    others = self.search([
                        ('id', '!=', rec.id),
                        ('consumption_mode', '=', 'daily'),
                        ('production_line_id', '=', line.id),
                        ('consumption_date', '=', cdate),
                        ('state', '!=', 'cancel'),
                    ], limit=1)
                    if others:
                        raise UserError(_(
                            'Ya existe otro consumo diario para %(line)s en %(date)s: %(cmp)s.',
                            line=line.display_name,
                            date=fields.Date.to_string(cdate),
                            cmp=others.display_name,
                        ))
                    if rec.state in self._kc_daily_open_states() or vals.get('state') in self._kc_daily_open_states():
                        blocking = self._kc_find_blocking_daily_cmp(line, cdate, company=rec.company_id)
                        if blocking and blocking.id != rec.id:
                            raise UserError(_(
                                'No puede usar la fecha %(date)s en %(line)s mientras '
                                '%(cmp)s del %(block_date)s siga abierto.',
                                date=fields.Date.to_string(cdate),
                                line=line.display_name,
                                cmp=blocking.display_name,
                                block_date=fields.Date.to_string(blocking.consumption_date),
                            ))
        return super().write(vals)

    @api.model
    def action_create_daily_cmp(self, production_line_id, consumption_date=None):
        """Crea un CMP diario y devuelve acción de formulario."""
        line = self.env['kc.production.line'].browse(production_line_id)
        if not line:
            raise UserError(_('Debe indicar una línea de producción.'))
        cdate = consumption_date or fields.Date.context_today(self)
        if isinstance(cdate, str):
            cdate = fields.Date.from_string(cdate)
        self._kc_assert_daily_can_create(line, cdate)
        cmp = self.sudo().with_context(kc_pin_authorized=True).create({
            'consumption_mode': 'daily',
            'production_line_id': line.id,
            'consumption_date': cdate,
            'company_id': line.company_id.id,
            'warehouse_id': self.env['stock.warehouse'].sudo().search([
                ('company_id', '=', line.company_id.id),
            ], limit=1).id,
            'consumption_completeness': 'completo',
            'notes': _('Consumo diario — %(line)s — %(date)s', line=line.name,
                       date=fields.Date.to_string(cdate)),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consumo Diario'),
            'res_model': 'kc.production.consumption',
            'view_mode': 'form',
            'res_id': cmp.id,
            'target': 'current',
        }

    @api.onchange('consumption_mode')
    def _onchange_consumption_mode(self):
        if self.consumption_mode == 'daily':
            if not self.consumption_date:
                self.consumption_date = fields.Date.context_today(self)
            self.entry_id = False

    @api.onchange('consumption_date')
    def _onchange_consumption_date_daily(self):
        if self.consumption_mode == 'daily' and self.consumption_date:
            day = self.consumption_date
            self.date_consumption = datetime.combine(day, time(12, 0, 0))

    @api.onchange('production_line_id')
    def _onchange_production_line_clear_work_center(self):
        if self.work_center_id and self.production_line_id:
            if self.work_center_id.production_line_id != self.production_line_id:
                self.work_center_id = False
        elif not self.production_line_id:
            self.work_center_id = False

    @api.depends('company_id')
    def _compute_picking_type_id(self):
        """Muestra el tipo de operación dedicado (CMP) de la compañía."""
        PickingType = self.env['stock.picking.type']
        for rec in self:
            rec.picking_type_id = PickingType.search([
                ('kc_production_role', '=', 'cmp'),
                ('company_id', '=', rec.company_id.id),
            ], limit=1)

    @api.depends('picking_type_id', 'warehouse_id', 'company_id')
    def _compute_location_id(self):
        """Origen MP del CMP: tipo de operación CMP, no lot_stock genérico."""
        for rec in self:
            rec.location_id = rec._kc_get_cmp_source_location()

    def _kc_get_cmp_source_location(self):
        """Ubicación origen del CMP (Materia Prima / Bodega MP)."""
        self.ensure_one()
        picking_type = self.picking_type_id or self._get_picking_type('cmp', 'outgoing')
        if picking_type.default_location_src_id:
            return picking_type.default_location_src_id
        mp_loc = self.env['kc.production.entry']._kc_resolve_named_stock_location(
            self.company_id, '%Bodega MP%')
        if mp_loc:
            return mp_loc
        if self.warehouse_id:
            return self.warehouse_id.lot_stock_id
        return self._get_warehouse().lot_stock_id

    @api.depends('picking_id', 'picking_id.move_line_ids')
    def _compute_move_line_count(self):
        """Cuenta las operaciones de inventario (move lines) del albarán."""
        for rec in self:
            rec.move_line_count = len(rec.picking_id.move_line_ids) if rec.picking_id else 0

    @api.depends('company_id', 'entry_id')
    def _compute_available_entry_ids(self):
        """RP confirmados/validados con consumo abierto (más el propio).

        Operadores de Bodega (sin rol gerente) solo ven RP de sus líneas
        asignadas; gerentes ven todos los RP abiertos de la compañía.
        """
        Entry = self.env['kc.production.entry']
        for rec in self:
            company = rec.company_id or self.env.company
            entries = Entry.search([
                ('state', 'in', ['confirmed', 'done']),
                ('consumption_closed', '=', False),
                ('company_id', '=', company.id),
            ])
            entries = Entry._kc_filter_entries_for_bodega_user(entries)
            if rec.entry_id:
                entries |= rec.entry_id
            rec.available_entry_ids = entries

    @api.model
    def _kc_sale_analytic_distribution(self, sale_order):
        """Distribución analítica derivada de una Orden de Venta.

        sale.order no tiene analytic_distribution directo: la analítica vive en
        el Proyecto (project_id.account_id). Prioridad: cuenta analítica del
        proyecto -> primera línea con distribución propia. False si no hay.
        """
        if not sale_order:
            return False
        project = getattr(sale_order, 'project_id', False)
        account = getattr(project, 'account_id', False) if project else False
        if account:
            return {str(account.id): 100.0}
        for line in sale_order.order_line:
            dist = getattr(line, 'analytic_distribution', False)
            if dist:
                return dist
        return False

    def _kc_get_account_moves(self):
        """Asientos contables (account.move) de valoración del albarán.

        Compatible con Odoo 18 (stock_valuation_layer_ids -> account_move_id) y
        Odoo 19 (stock.move.account_move_id directo).
        """
        self.ensure_one()
        AccountMove = self.env['account.move']
        moves = AccountMove
        if self.picking_id:
            for sm in self.picking_id.move_ids:
                if 'account_move_id' in sm._fields and sm.account_move_id:
                    moves |= sm.account_move_id
                if 'stock_valuation_layer_ids' in sm._fields:
                    moves |= sm.stock_valuation_layer_ids.mapped('account_move_id')
        # Incluye los asientos manuales de las líneas de servicio.
        moves |= self.kc_service_move_ids
        return moves

    @api.depends('picking_id')
    def _compute_account_move_count(self):
        """Cuenta los asientos contables asociados (con sudo para operadores)."""
        for rec in self:
            rec.account_move_count = len(rec.sudo()._kc_get_account_moves())

    def _check_account_access(self):
        """Solo gerentes de producción o de inventario pueden ver asientos."""
        if not (self.env.user.has_group('kc_manual_production.kc_production_group_manager')
                or self.env.user.has_group('stock.group_stock_manager')):
            raise AccessError(_(
                "No tiene permisos para consultar los asientos contables de este "
                "documento. Esta acción está restringida a administradores."))

    def action_view_account_moves(self):
        """Botón inteligente (solo admin): abre el/los asientos de valoración."""
        self.ensure_one()
        self._check_account_access()
        moves = self._kc_get_account_moves()
        if not moves:
            raise UserError(_("Este consumo no tiene asientos contables asociados."))
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Asientos Contables'),
            'res_model': 'account.move',
            'target': 'current',
        }
        if len(moves) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': moves.id,
                'views': [[False, 'form']],
            })
        else:
            action.update({
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': [('id', 'in', moves.ids)],
            })
        return action

    @api.depends('reversal_of_id')
    def _compute_is_reversal(self):
        """True si este consumo es a su vez una reversión de otro."""
        for rec in self:
            rec.is_reversal = bool(rec.reversal_of_id)

    def _compute_reversed_by_id(self):
        """Busca si existe un consumo que revierte a este (sin almacenar)."""
        for rec in self:
            rec.reversed_by_id = self.search(
                [('reversal_of_id', '=', rec.id)], limit=1) if rec.id else False

    @api.onchange('entry_id')
    def _onchange_entry_id(self):
        """Autocompleta la OV desde el RP, sin borrarla si se limpia el RP."""
        if self.entry_id and self.entry_id.sale_order_id:
            self.sale_order_id = self.entry_id.sale_order_id

    @api.onchange('entry_id', 'sale_order_id')
    def _onchange_kc_analytic_distribution(self):
        """Propone la distribución analítica heredada y la mantiene al día.

        La fuente es la OV del RP vinculado o, si no hay RP, la OV directa.
        La propuesta SIGUE a la fuente (cambiar de RP/OV recalcula) mientras el
        usuario no haya hecho un reparto manual. En cuanto el reparto difiere del
        último valor heredado, se considera manual y ya no se sobrescribe.
        """
        sale_order = (self.entry_id.sale_order_id if self.entry_id else False) \
            or self.sale_order_id
        propuesta = self._kc_sale_analytic_distribution(sale_order)
        # Re-propone solo si el usuario no personalizó el reparto: el valor actual
        # está vacío o coincide con la última herencia registrada.
        if not self.analytic_distribution or \
                self.analytic_distribution == self.kc_analytic_inherited:
            self.analytic_distribution = propuesta
        self.kc_analytic_inherited = propuesta

    def action_confirm(self):
        """Confirma el CMP: valida stock por línea y luego asigna la secuencia.

        La validación de stock se ejecuta ANTES de tomar el número de secuencia
        para no "quemar" un consecutivo cuando falta inventario.
        """
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Debe agregar al menos una línea de materia prima antes de confirmar."))

            # 1) Validación de stock por línea (SOLO material; los servicios no
            #    mueven inventario y se excluyen por completo de esta validación).
            errores = []
            for line in rec.line_ids:
                if not line.product_id:
                    raise UserError(_("Todas las líneas deben tener un producto definido."))
                if line.line_type == 'service':
                    continue
                # El lote solo es obligatorio para productos rastreados por lote.
                if line.product_id.tracking == 'lot' and not line.lot_id:
                    raise UserError(_(
                        "El producto %s se rastrea por lote: debe indicar el lote a consumir."
                    ) % line.product_id.display_name)
                disponible = rec._get_stock_disponible(
                    line.product_id, line.lot_id, rec.company_id)
                if disponible < line.qty:
                    errores.append(_(
                        "- %(prod)s (lote %(lot)s): disponible %(disp)s, requerido %(req)s",
                        prod=line.product_id.display_name,
                        lot=line.lot_id.name or '-',
                        disp=disponible,
                        req=line.qty,
                    ))
            if errores:
                raise UserError(
                    _("Stock insuficiente para confirmar el consumo:\n\n%s") % "\n".join(errores))

            # 2) Si todo OK, asigna la secuencia y confirma.
            if rec.name == '/' or not rec.name:
                rec.name = self.env['ir.sequence'].next_by_code('kc.production.consumption') or '/'
            rec.state = 'confirmed'
        return True

    def _get_warehouse(self):
        """Devuelve el almacén de la compañía del consumo (o lanza error)."""
        self.ensure_one()
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.company_id.id)], limit=1)
        if not warehouse:
            raise UserError(_("No se encontró un almacén para la compañía %s.") % self.company_id.name)
        return warehouse

    def _get_production_location(self):
        """Ubicación virtual de Producción de la compañía (multi-compañía)."""
        self.ensure_one()
        loc = self.env['stock.location'].search([
            ('usage', '=', 'production'),
            ('company_id', 'in', [self.company_id.id, False]),
        ], order='company_id desc', limit=1)
        if not loc:
            loc = self.env.ref('stock.location_production', raise_if_not_found=False)
        if not loc:
            raise UserError(_("No se encontró una ubicación de Producción para la compañía %s.") % self.company_id.name)
        return loc

    def _get_picking_type(self, role, code):
        """Devuelve el tipo de operación dedicado por rol (rp/cmp).

        Si no existe, se crea automáticamente con la configuración correcta.
        Como respaldo, usa el tipo estándar del 'code' indicado.
        """
        self.ensure_one()
        picking_type = self.env['stock.picking.type']._kc_get_or_create_production_type(
            role, self.company_id)
        if not picking_type:
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', code),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
        if not picking_type:
            raise UserError(_("No se encontró un tipo de operación '%(code)s' para la compañía %(company)s.",
                              code=code, company=self.company_id.name))
        return picking_type

    def _create_stock_picking(self, location_src, location_dest, picking_type):
        """Crea y valida un stock.picking con las líneas del consumo.

        Reutilizado por la validación normal (salida) y por la reversión
        (entrada en sentido inverso). Usa el lote de cada línea.
        """
        self.ensure_one()
        # Solo las líneas de material mueven inventario. Si no hay material
        # (CMP solo de servicios), no se crea albarán.
        material_lines = self.line_ids.filtered(lambda l: l._kc_moves_inventory())
        if not material_lines:
            return self.env['stock.picking']
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': location_src.id,
            'location_dest_id': location_dest.id,
            'origin': self.name,
            'partner_id': self.partner_id.id or False,
            'company_id': self.company_id.id,
        })
        for line in material_lines:
            move = self.env['stock.move'].create({
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'product_uom': line.uom_id.id,
                'picking_id': picking.id,
                'location_id': location_src.id,
                'location_dest_id': location_dest.id,
                'company_id': self.company_id.id,
                # Traza el origen para propagar la analítica del CMP al asiento.
                'kc_production_consumption_id': self.id,
            })
            self.env['stock.move.line'].create({
                'move_id': move.id,
                'picking_id': picking.id,
                'product_id': line.product_id.id,
                'product_uom_id': line.uom_id.id,
                'location_id': location_src.id,
                'location_dest_id': location_dest.id,
                'lot_id': line.lot_id.id,
                'quantity': line.qty,
                'picked': True,
                'company_id': self.company_id.id,
            })
        picking.action_confirm()
        result = picking.with_context(skip_backorder=True).button_validate()
        # button_validate puede devolver una acción (asistente). Si es la
        # confirmación de backorder, la procesamos SIN crear backorder.
        if isinstance(result, dict) and result.get('res_model') == 'stock.backorder.confirmation':
            wizard = self.env['stock.backorder.confirmation'].with_context(
                result.get('context', {})).create({})
            wizard.process_cancel_backorder()
        # Guarda de integridad: si el albarán no quedó 'done', el inventario NO
        # se movió; abortamos para no marcar el consumo como validado en falso.
        if picking.state != 'done':
            raise UserError(_(
                "No se pudo completar el movimiento de inventario "
                "(albarán %(name)s, estado %(state)s). Revise stock y ubicaciones.",
                name=picking.name, state=picking.state))
        return picking

    def action_validate(self):
        """Valida el CMP: picking de SALIDA para material + asiento para servicios."""
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(_("Solo se pueden validar consumos en estado 'Confirmado'."))
            if not rec.line_ids:
                raise UserError(_("No hay líneas para validar."))

            material_lines = rec.line_ids.filtered(lambda l: l._kc_moves_inventory())
            if material_lines:
                location_src = rec._kc_get_cmp_source_location()
                location_dest = rec._get_production_location()
                picking_type = rec.picking_type_id or rec._get_picking_type('cmp', 'outgoing')
                picking = rec._create_stock_picking(location_src, location_dest, picking_type)
                if picking:
                    rec.picking_id = picking.id

            # Líneas de servicio: asiento contable manual (no mueven inventario).
            rec._kc_create_service_account_move()

            rec.state = 'done'
        return True

    def _kc_get_service_journal(self):
        """Diario para los asientos de servicio (diario general de la compañía)."""
        self.ensure_one()
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_(
                "No se encontró un diario de tipo 'General' para la compañía %s."
            ) % self.company_id.name)
        return journal

    def _kc_get_service_counterpart_account(self):
        """Cuenta de CONTRAPARTIDA (HABER) del asiento de servicio.

        PENDIENTE DE DEFINICIÓN CONTABLE (Jorge): depende de la política del
        cliente (cuenta puente de producción, cuenta por pagar genérica, etc.).
        Mientras no esté definida, se bloquea la generación del asiento para no
        registrar contabilidad incorrecta.
        """
        self.ensure_one()
        # TODO(Jorge): reemplazar por la cuenta contrapartida real una vez
        # confirmada la política contable (p. ej. una cuenta puente fija por
        # compañía, un campo de configuración, o la cuenta por pagar).
        raise UserError(_(
            "Falta definir la cuenta de contrapartida del asiento de servicios. "
            "Confirme con contabilidad qué cuenta debe usarse en el HABER antes "
            "de validar consumos con líneas de servicio."))

    def _kc_create_service_account_move(self, reverse=False):
        """Genera (o revierte) el asiento contable de las líneas de servicio.

        DEBE: cuenta de gasto del producto de servicio (con la analítica de la
        cabecera del CMP). HABER: cuenta de contrapartida (ver método dedicado).
        En reversión se invierten DEBE/HABER para netear el original.
        """
        self.ensure_one()
        service_lines = self.line_ids.filtered(
            lambda l: l.line_type == 'service' and l.service_value)
        if not service_lines:
            return self.env['account.move']

        journal = self._kc_get_service_journal()
        counterpart = self._kc_get_service_counterpart_account()
        distribution = self.analytic_distribution or False

        debit_lines = []
        total = 0.0
        for line in service_lines:
            accounts = line.product_id.product_tmpl_id._get_product_accounts()
            expense_account = accounts.get('expense')
            if not expense_account:
                raise UserError(_(
                    "El producto de servicio %s no tiene cuenta de gasto "
                    "configurada (ni en el producto ni en su categoría)."
                ) % line.product_id.display_name)
            amount = line.service_value
            total += amount
            # En reversión, el gasto va al HABER (se revierte).
            debit_lines.append((0, 0, {
                'name': line.product_id.display_name,
                'account_id': expense_account.id,
                'debit': 0.0 if reverse else amount,
                'credit': amount if reverse else 0.0,
                'analytic_distribution': distribution,
            }))

        counterpart_line = (0, 0, {
            'name': _('Contrapartida servicios %s') % self.name,
            'account_id': counterpart.id,
            'debit': total if reverse else 0.0,
            'credit': 0.0 if reverse else total,
        })

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'company_id': self.company_id.id,
            'date': fields.Date.context_today(self),
            'ref': _('Servicios CMP %s%s') % (self.name, _(' (Reversión)') if reverse else ''),
            'line_ids': debit_lines + [counterpart_line],
        })
        move.action_post()
        self.kc_service_move_ids = [(4, move.id)]
        return move

    def action_open_reversal_wizard(self):
        """Abre el wizard de confirmación de reversión con el CMP precargado."""
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_("Solo se pueden revertir consumos validados."))
        if self.is_reversal:
            raise UserError(_("Una reversión no puede revertirse de nuevo."))
        if self.reversed_by_id:
            raise UserError(_("Este consumo ya fue revertido por %s.") % self.reversed_by_id.name)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Revertir Consumo de Materia Prima'),
            'res_model': 'kc.production.consumption.reversal.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_consumption_id': self.id},
        }

    def create_reversal(self, reason):
        """Crea un CMP de reversión en estado 'done' con picking inverso.

        El picking de reversión va Producción → Stock (la MP "regresa" al
        almacén), usando el MISMO lote para conservar el historial.
        """
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_("Solo se pueden revertir consumos validados."))
        if self.is_reversal:
            raise UserError(_("Una reversión no puede revertirse de nuevo."))
        if self.reversed_by_id:
            raise UserError(_("Este consumo ya fue revertido por %s.") % self.reversed_by_id.name)

        reversal = self.create({
            'reversal_of_id': self.id,
            'notes_reversal': reason,
            'entry_id': self.entry_id.id or False,
            'sale_order_id': self.sale_order_id.id or False,
            'partner_id': self.partner_id.id or False,
            'company_id': self.company_id.id,
            'warehouse_id': self.warehouse_id.id or False,
            'date_consumption': fields.Datetime.now(),
            # La reversión hereda EXACTAMENTE la analítica del original, para que
            # la línea analítica inversa netee a cero contra la original.
            'analytic_distribution': self.analytic_distribution or False,
            'line_ids': [(0, 0, {
                'line_type': line.line_type,
                'product_id': line.product_id.id,
                'lot_id': line.lot_id.id,
                'qty': line.qty,
                'uom_id': line.uom_id.id,
                'service_value': line.service_value,
                'service_value_manual': line.service_value_manual,
            }) for line in self.line_ids],
        })
        reversal.name = self.env['ir.sequence'].next_by_code('kc.production.consumption') or '/'

        # Picking inverso solo si hay material: Producción → Stock (tipo RP).
        if reversal.line_ids.filtered(lambda l: l._kc_moves_inventory()):
            location_src = reversal._get_production_location()
            location_dest = reversal._kc_get_cmp_source_location()
            picking_type = reversal._get_picking_type('rp', 'incoming')
            picking = reversal._create_stock_picking(location_src, location_dest, picking_type)
            if picking:
                reversal.picking_id = picking.id

        # Asiento inverso de las líneas de servicio (netea el original).
        reversal._kc_create_service_account_move(reverse=True)
        reversal.state = 'done'
        reversal.message_post(body=_("Reversión del consumo %s. Motivo: %s") % (self.name, reason))
        self.message_post(body=_("Consumo revertido por %s.") % reversal.name)
        return reversal

    def action_cancel(self):
        """Cancela el CMP. No permitido si ya fue validado (state='done')."""
        for rec in self:
            if rec.state == 'done':
                raise UserError(_("No se puede cancelar un consumo ya validado."))
            rec.state = 'cancel'
        return True

    def action_draft(self):
        """Regresa un consumo cancelado a borrador."""
        for rec in self:
            if rec.state == 'cancel':
                rec.state = 'draft'
        return True

    def action_view_picking(self):
        """Abre el albarán de salida relacionado (botón inteligente)."""
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_("Este consumo aún no tiene un albarán generado."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Albarán de Salida'),
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.picking_id.id,
            'target': 'current',
        }

    def action_view_sale_order(self):
        """Botón inteligente: abre la Orden de Venta vinculada."""
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_("Este consumo no está vinculado a una Orden de Venta."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Orden de Venta'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
            'target': 'current',
        }

    def action_view_stock_moves(self):
        """Botón inteligente: abre los movimientos de inventario del albarán."""
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_("Este consumo aún no tiene movimientos de inventario."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Movimientos de Inventario'),
            'res_model': 'stock.move.line',
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('picking_id', '=', self.picking_id.id)],
            'context': {'create': False, 'edit': False},
            'target': 'current',
        }

    def action_view_entry(self):
        """Botón inteligente: abre el Registro de Producción vinculado."""
        self.ensure_one()
        if not self.entry_id:
            raise UserError(_("Este consumo no está vinculado a un Registro de Producción."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registro de Producción'),
            'res_model': 'kc.production.entry',
            'view_mode': 'form',
            'res_id': self.entry_id.id,
            'target': 'current',
        }

    @api.model
    def _get_stock_disponible(self, product, lot, company):
        """Suma la cantidad física en ubicaciones internas para producto+lote."""
        dominio = [
            ('product_id', '=', product.id),
            ('location_id.usage', '=', 'internal'),
            ('company_id', '=', company.id),
        ]
        if lot:
            dominio.append(('lot_id', '=', lot.id))
        quants = self.env['stock.quant'].search(dominio)
        return sum(quants.mapped('quantity'))


class KcProductionConsumptionLine(models.Model):
    """Línea de Consumo de Materia Prima: una MP con su lote existente."""
    _name = 'kc.production.consumption.line'
    _description = 'Línea de Consumo de Materia Prima'

    consumption_id = fields.Many2one(
        comodel_name='kc.production.consumption',
        string='Consumo de MP',
        required=True,
        ondelete='cascade',
    )
    line_type = fields.Selection(
        selection=[
            ('material', 'Materia Prima'),
            ('supply', 'Insumo'),
            ('service', 'Servicio'),
        ],
        string='Tipo',
        default='material',
        required=True,
        help="Materia Prima e Insumo mueven inventario; Servicio no mueve "
             "inventario y genera un asiento contable de costo por su valor.",
    )
    kc_allowed_product_ids = fields.Many2many(
        comodel_name='product.product',
        compute='_compute_kc_allowed_product_ids',
        string='Productos permitidos',
        help="Dominio dinámico según el tipo de línea y las categorías configuradas.",
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Producto',
        required=True,
        domain="[('id', 'in', kc_allowed_product_ids)]",
        help="Materia Prima: productos de la categoría MP. Insumo: categoría "
             "INSUMOS. Servicio: productos tipo servicio.",
    )
    product_tracking = fields.Selection(
        related='product_id.tracking',
        string='Trazabilidad',
    )
    lot_id = fields.Many2one(
        comodel_name='stock.lot',
        string='Lote',
        domain="[('product_id', '=', product_id)]",
        help="Obligatorio solo si el producto se rastrea por lote (líneas de material).",
    )
    qty = fields.Float(
        string='Cantidad',
        required=True,
        default=0.0,
        digits='Product Unit of Measure',
    )
    uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string='Unidad de Medida',
        related='product_id.uom_id',
        store=True,
        readonly=False,
    )
    qty_available = fields.Float(
        string='Disponible',
        compute='_compute_qty_available',
        digits='Product Unit of Measure',
        help="Stock físico total del producto+lote en ubicaciones internas.",
    )
    currency_id = fields.Many2one(
        related='consumption_id.company_id.currency_id',
        string='Moneda',
        readonly=True,
    )
    service_value = fields.Monetary(
        string='Valor del Servicio',
        currency_field='currency_id',
        help="Costo del servicio a cargar. Se sugiere cantidad x costo estándar, "
             "pero es editable libremente por el operador.",
    )
    service_value_manual = fields.Boolean(
        string='Valor de Servicio Manual',
        default=False,
        help="Uso interno: marca que el operador editó el valor del servicio, "
             "para no sobrescribir la sugerencia automática.",
    )

    def _kc_moves_inventory(self):
        """True si la línea genera movimiento de inventario (MP o Insumo)."""
        self.ensure_one()
        return self.line_type in ('material', 'supply')

    def _kc_get_mp_category(self):
        company = self.consumption_id.company_id or self.env.company
        return company._kc_cmp_resolve_mp_category()

    def _kc_get_supply_category(self):
        company = self.consumption_id.company_id or self.env.company
        return company._kc_cmp_resolve_supply_category()

    def _kc_product_domain_for_type(self):
        """Dominio de búsqueda de productos según line_type."""
        self.ensure_one()
        if self.line_type == 'service':
            return [('type', '=', 'service')]
        if self.line_type == 'supply':
            categ = self._kc_get_supply_category()
            if not categ:
                return [('id', '=', False)]
            return [
                ('categ_id', 'child_of', categ.id),
                ('type', 'in', ('consu', 'product')),
            ]
        categ = self._kc_get_mp_category()
        if not categ:
            return [('id', '=', False)]
        return [
            ('categ_id', 'child_of', categ.id),
            ('type', 'in', ('consu', 'product')),
        ]

    @api.depends('line_type', 'consumption_id.company_id')
    def _compute_kc_allowed_product_ids(self):
        Product = self.env['product.product']
        for line in self:
            line.kc_allowed_product_ids = Product.search(line._kc_product_domain_for_type())

    @api.constrains('line_type', 'product_id')
    def _check_product_matches_line_type(self):
        ProductionLine = self.env['kc.production.line']
        for line in self:
            if not line.product_id:
                continue
            if line.line_type == 'service':
                if line.product_id.type != 'service':
                    raise ValidationError(_(
                        "En líneas de Servicio solo puede seleccionar productos "
                        "tipo servicio (producto: %(product)s).",
                        product=line.product_id.display_name,
                    ))
                continue
            expected_categ = (
                line._kc_get_supply_category()
                if line.line_type == 'supply'
                else line._kc_get_mp_category()
            )
            if not expected_categ:
                label = _('Insumo') if line.line_type == 'supply' else _('Materia Prima')
                raise ValidationError(_(
                    "No está configurada la categoría raíz para líneas de %(label)s.",
                    label=label,
                ))
            if not ProductionLine._kc_product_matches_categ(
                    line.product_id.categ_id, expected_categ):
                raise ValidationError(_(
                    "El producto %(product)s no pertenece a la categoría esperada "
                    "para líneas de %(label)s.",
                    product=line.product_id.display_name,
                    label=dict(line._fields['line_type'].selection).get(
                        line.line_type, line.line_type),
                ))

    @api.depends('product_id', 'lot_id', 'line_type')
    def _compute_qty_available(self):
        """Calcula al vuelo el stock disponible (solo aplica a material)."""
        for line in self:
            if line.line_type == 'service' or not line.product_id:
                line.qty_available = 0.0
                continue
            company = line.consumption_id.company_id or self.env.company
            dominio = [
                ('product_id', '=', line.product_id.id),
                ('location_id.usage', '=', 'internal'),
                ('company_id', '=', company.id),
            ]
            if line.lot_id:
                dominio.append(('lot_id', '=', line.lot_id.id))
            quants = self.env['stock.quant'].search(dominio)
            line.qty_available = sum(quants.mapped('quantity'))

    def _kc_suggest_service_value(self):
        """Sugiere service_value = cantidad x costo estándar (si no es manual)."""
        for line in self:
            if line.line_type == 'service' and line.product_id and not line.service_value_manual:
                line.service_value = line.qty * line.product_id.standard_price

    @api.onchange('line_type')
    def _onchange_line_type(self):
        """Al cambiar tipo: limpia producto y ajusta campos de servicio/lote."""
        self.product_id = False
        self.lot_id = False
        if self.line_type == 'service':
            self.service_value_manual = False
            self._kc_suggest_service_value()
        else:
            self.service_value = 0.0
            self.service_value_manual = False

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Limpia el lote y re-sugiere el valor de servicio al cambiar producto."""
        self.lot_id = False
        if self.line_type == 'service':
            # Producto nuevo -> vuelve a sugerir desde su costo estándar.
            self.service_value_manual = False
            self._kc_suggest_service_value()

    @api.onchange('qty')
    def _onchange_qty_service(self):
        """Re-sugiere el valor de servicio según la cantidad (si no es manual)."""
        if self.line_type == 'service':
            self._kc_suggest_service_value()

    @api.onchange('service_value')
    def _onchange_service_value(self):
        """Marca el valor como manual cuando el operador lo edita directamente."""
        if self.line_type == 'service':
            self.service_value_manual = True
