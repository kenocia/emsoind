# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError, AccessError
from odoo.tools.float_utils import float_compare, float_is_zero


class KcProductionEntry(models.Model):
    """Registro de Producción (RP).

    Representa la ENTRADA de Producto Terminado al inventario mediante un
    stock.picking de tipo entrada generado programáticamente. Es una solución
    transitoria de control de producción sin el módulo MRP de Odoo.
    """
    _name = 'kc.production.entry'
    _description = 'Registro de Producción Manual'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'analytic.mixin']
    _order = 'date_production desc, id desc'

    name = fields.Char(
        string='Referencia',
        default='/',
        readonly=True,
        copy=False,
        index=True,
        help="Se asigna automáticamente desde la secuencia al confirmar el registro.",
    )
    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Orden de Venta',
        domain="[('state', 'in', ['sale', 'done'])]",
        help="Orden de Venta opcional a la que se vincula esta producción.",
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Cliente',
        related='sale_order_id.partner_id',
        store=True,
        readonly=False,
        help="Se hereda de la Orden de Venta; editable manualmente si no hay OV.",
    )
    date_production = fields.Datetime(
        string='Fecha de Producción',
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
        comodel_name='kc.production.entry.line',
        inverse_name='entry_id',
        string='Líneas de Producto Terminado',
        copy=True,
    )
    picking_id = fields.Many2one(
        comodel_name='stock.picking',
        string='Albarán de Entrada',
        readonly=True,
        copy=False,
        help="Movimiento de inventario generado al validar el registro.",
    )
    consumption_ids = fields.One2many(
        comodel_name='kc.production.consumption',
        inverse_name='entry_id',
        string='Consumos MP relacionados',
    )
    consumption_count = fields.Integer(
        string='N° Consumos',
        compute='_compute_consumption_count',
    )
    consumption_closed = fields.Boolean(
        string='Consumo Cerrado',
        compute='_compute_consumption_closed',
        store=True,
        help="El consumo de materia prima de este Registro de Producción fue "
             "marcado como COMPLETO en un CMP confirmado/validado. Cuando está "
             "cerrado, el RP ya no aparece para registrar nuevos consumos.",
    )
    available_sale_order_ids = fields.Many2many(
        comodel_name='sale.order',
        string='Órdenes de Venta disponibles',
        compute='_compute_available_sale_order_ids',
        help="Órdenes de Venta que aún no tienen un Registro de Producción "
             "activo. Se usa para filtrar el selector de OV.",
    )
    available_production_line_ids = fields.Many2many(
        comodel_name='kc.production.line',
        string='Líneas de Producción disponibles',
        compute='_compute_available_production_line_ids',
        help="Líneas que el usuario actual puede asignar a este registro.",
    )
    move_line_count = fields.Integer(
        string='N° Movimientos',
        compute='_compute_move_line_count',
    )
    account_move_count = fields.Integer(
        string='N° Asientos',
        compute='_compute_account_move_count',
    )
    # Redefine el campo del analytic.mixin: en el RP NO es editable, se hereda
    # SIEMPRE de la Orden de Venta (proyecto/cuenta analítica). Si no hay OV,
    # queda vacío y no se propaga ninguna analítica.
    analytic_distribution = fields.Json(
        string='Distribución Analítica',
        compute='_compute_analytic_distribution',
        store=True,
        readonly=True,
        copy=True,
        help="Heredada automáticamente del Proyecto/cuenta analítica de la "
             "Orden de Venta. No editable: el PT pertenece a la OV que lo originó.",
    )
    notes = fields.Text(string='Notas')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Moneda',
        readonly=True,
    )
    # ---- Origen del RP: OV / Abastecimiento / Manual ----------------------
    created_from_replenishment = fields.Boolean(
        string='Creado desde Abastecimiento',
        default=False,
        readonly=True,
        copy=False,
        help="Marca técnica: el RP fue generado desde el asistente de "
             "Abastecimiento (reglas de reabastecimiento), no desde una OV.",
    )
    origin_type = fields.Selection(
        selection=[
            ('sale_order', 'Orden de Venta'),
            ('replenishment', 'Abastecimiento'),
            ('manual', 'Manual'),
        ],
        string='Origen',
        default='manual',
        compute='_compute_origin_type',
        store=True,
    )
    # ---- Comparativo de costo PT vs. consumo real (solo lectura) ----------
    registered_pt_cost = fields.Monetary(
        string='Costo Registrado PT',
        compute='_compute_cost_comparison',
        currency_field='currency_id',
        help="Suma de cantidad x costo unitario asignado en las líneas de PT del RP.",
    )
    real_consumption_cost = fields.Monetary(
        string='Costo Real Consumido',
        compute='_compute_cost_comparison',
        currency_field='currency_id',
        help="Suma del costo de MP y servicios de los consumos (CMP) validados "
             "vinculados a este RP.",
    )
    cost_difference = fields.Monetary(
        string='Diferencia',
        compute='_compute_cost_comparison',
        currency_field='currency_id',
        help="Costo real consumido menos costo registrado del PT. Positivo = se "
             "gastó más en MP/servicios de lo que vale el PT a costo estándar.",
    )
    kc_has_cost_above_sale = fields.Boolean(
        string='Costo supera precio de venta',
        compute='_compute_kc_has_cost_above_sale',
        help="Indica si alguna línea tiene costo unitario mayor al precio neto "
             "de la Orden de Venta vinculada.",
    )
    kc_total_weight = fields.Float(
        string='Peso total (kg)',
        compute='_compute_kc_entry_weight_area_totals',
        digits='Stock Weight',
    )
    kc_total_area_sqft = fields.Float(
        string='Área total (FT²)',
        compute='_compute_kc_entry_weight_area_totals',
        digits=(16, 4),
    )
    production_line_id = fields.Many2one(
        comodel_name='kc.production.line',
        string='Línea de Producción',
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
        required=True,
        tracking=True,
        help="Línea responsable de este registro. Solo la ven los operadores "
             "asignados a esa línea.",
    )
    work_center_id = fields.Many2one(
        comodel_name='kc.work.center',
        string='Centro de Trabajo',
        domain="[('production_line_id', '=', production_line_id), "
               "('state', '=', 'active'), ('active', '=', True)]",
        tracking=True,
        help="Centro opcional donde se ejecuta la producción.",
    )
    plan_line_id = fields.Many2one(
        comodel_name='kc.production.plan.line',
        string='Bloque de Planificación',
        readonly=True,
        copy=False,
        help="Bloque del Gantt que originó este RP (si aplica).",
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Bodega',
        default=lambda self: self._default_warehouse_id(),
        domain="[('company_id', '=', company_id)]",
        required=True,
        help="Almacén donde se registra la entrada del Producto Terminado.",
    )
    picking_type_id = fields.Many2one(
        comodel_name='stock.picking.type',
        string='Tipo de Operación',
        compute='_compute_picking_type_id',
        readonly=True,
        help="Tipo de operación de Producción Manual (RP) usado al validar.",
    )
    location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Ubicación de Bodega PT',
        compute='_compute_location_id',
        help="Ubicación de destino donde ingresa el Producto Terminado "
             "(según el tipo de operación RP).",
    )

    # ---- Campos de reversión (corrección tipo "nota de crédito") ----------
    reversal_of_id = fields.Many2one(
        comodel_name='kc.production.entry',
        string='Reversión de',
        readonly=True,
        copy=False,
        help="Registro de Producción original que este documento revierte.",
    )
    reversed_by_id = fields.Many2one(
        comodel_name='kc.production.entry',
        string='Revertido por',
        compute='_compute_reversed_by_id',
        help="Registro de reversión que anula el efecto de este documento.",
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

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'production_line_id' in fields_list and not res.get('production_line_id'):
            line_id = self._default_production_line_id()
            if line_id:
                res['production_line_id'] = line_id
        return res

    @api.model
    def _default_warehouse_id(self):
        """Primer almacén de la compañía activa como bodega por defecto."""
        return self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)

    @api.model
    def _kc_resolve_production_line_for_products(self, products, company=None):
        """Devuelve la línea de producción más adecuada para un conjunto de PT."""
        company = company or self.env.company
        if not products:
            return self.env['kc.production.line']
        Line = self.env['kc.production.line']
        counts = {}
        for product in products:
            line = Line.resolve_for_product(product, company=company)
            if line:
                counts[line.id] = counts.get(line.id, 0) + 1
        if not counts:
            return self.env['kc.production.line']
        if len(counts) == 1:
            return Line.browse(next(iter(counts)))
        best_id = max(counts, key=counts.get)
        return Line.browse(best_id)

    @api.model
    def _kc_resolve_production_line_id_from_vals(self, vals):
        """Intenta inferir production_line_id desde las líneas del RP o fallback."""
        product_ids = []
        for cmd in vals.get('line_ids', []):
            if isinstance(cmd, (list, tuple)) and len(cmd) >= 3 and cmd[0] == 0:
                product_id = cmd[2].get('product_id')
                if product_id:
                    product_ids.append(product_id)
        company = (
            self.env['res.company'].browse(vals['company_id'])
            if vals.get('company_id') else self.env.company
        )
        if product_ids:
            line = self._kc_resolve_production_line_for_products(
                self.env['product.product'].browse(product_ids),
                company=company,
            )
            if line:
                return line.id
        Line = self.env['kc.production.line']
        com_line = Line.search([
            ('company_id', '=', company.id),
            ('active', '=', True),
            ('code', '=', 'COM'),
        ], limit=1)
        if com_line:
            return com_line.id
        fallback = Line.search([
            ('company_id', '=', company.id),
            ('active', '=', True),
        ], order='sequence, id', limit=1)
        return fallback.id if fallback else False

    @api.model
    def _default_production_line_id(self):
        """Preselecciona la línea si el usuario pertenece a una sola."""
        if 'kc.production.line' not in self.env:
            return False
        lines = self.env.user.kc_production_line_ids.filtered(
            lambda l: l.company_id == self.env.company and l.active)
        return lines.id if len(lines) == 1 else False

    @api.model
    def _kc_user_is_production_manager(self):
        user = self.env.user
        return (
            user.has_group('kc_manual_production.kc_production_group_manager')
            or user.has_group('stock.group_stock_manager')
        )

    @api.model
    def _kc_production_line_domain_for_user(self, company=None):
        """Dominio de líneas que el usuario actual puede asignar a un RP."""
        company = company or self.env.company
        if self._kc_user_is_production_manager():
            return [('company_id', '=', company.id), ('active', '=', True)]
        return [
            ('company_id', '=', company.id),
            ('active', '=', True),
            ('user_ids', 'in', self.env.user.id),
        ]

    @api.model
    def _kc_filter_entries_for_bodega_user(self, entries):
        """Restringe RP visibles al crear CMP para bodegueros por línea."""
        if self._kc_user_is_production_manager():
            return entries
        if not self.env.user.has_group('kc_manual_production.kc_production_group_bodega'):
            return entries
        return entries.filtered(
            lambda e: self.env.user in e.production_line_id.user_ids
        )

    @api.model
    def _kc_apply_production_line_filter(self, domain, production_line_id):
        """Añade filtro de línea al dominio si se indicó."""
        if production_line_id:
            domain.append(('production_line_id', '=', production_line_id))
        return domain

    @api.constrains('production_line_id', 'company_id')
    def _check_production_line_access(self):
        """Operadores solo pueden usar líneas donde están asignados."""
        for rec in self:
            if not rec.production_line_id:
                continue
            if rec.production_line_id.company_id != rec.company_id:
                raise ValidationError(_(
                    'La línea de producción debe pertenecer a la misma compañía '
                    'del registro.'))
            if self._kc_user_is_production_manager():
                continue
            if self.env.user not in rec.production_line_id.user_ids:
                raise ValidationError(_(
                    'No está autorizado para asignar la línea de producción '
                    '"%(line)s".',
                    line=rec.production_line_id.name,
                ))

    @api.depends('company_id')
    def _compute_picking_type_id(self):
        """Muestra el tipo de operación dedicado (RP) de la compañía."""
        PickingType = self.env['stock.picking.type']
        for rec in self:
            rec.picking_type_id = PickingType.search([
                ('kc_production_role', '=', 'rp'),
                ('company_id', '=', rec.company_id.id),
            ], limit=1)

    @api.depends('picking_type_id', 'warehouse_id', 'company_id')
    def _compute_location_id(self):
        """Destino PT del RP: tipo de operación RP, no lot_stock del almacén."""
        for rec in self:
            rec.location_id = rec._kc_get_rp_destination_location()

    @api.model
    def _kc_resolve_named_stock_location(self, company, name_pattern):
        """Busca ubicación interna por patrón en complete_name (ej. Bodega PT)."""
        if not company or not name_pattern:
            return self.env['stock.location']
        return self.env['stock.location'].search([
            ('usage', '=', 'internal'),
            ('company_id', '=', company.id),
            ('complete_name', 'ilike', name_pattern),
        ], limit=1)

    def _kc_get_rp_destination_location(self):
        """Ubicación destino del RP (Producto Terminado / Bodega PT)."""
        self.ensure_one()
        picking_type = self.picking_type_id or self._get_picking_type('rp', 'incoming')
        if picking_type.default_location_dest_id:
            return picking_type.default_location_dest_id
        pt_loc = self._kc_resolve_named_stock_location(
            self.company_id, '%Bodega PT%')
        if pt_loc:
            return pt_loc
        if self.warehouse_id:
            return self.warehouse_id.lot_stock_id
        return self._get_warehouse().lot_stock_id

    @api.depends('consumption_ids')
    def _compute_consumption_count(self):
        """Cuenta los consumos de MP vinculados para el botón inteligente."""
        for rec in self:
            rec.consumption_count = len(rec.consumption_ids)

    @api.depends('consumption_ids.state', 'consumption_ids.consumption_completeness')
    def _compute_consumption_closed(self):
        """Cierra el RP cuando un CMP activo lo marca con consumo COMPLETO."""
        for rec in self:
            rec.consumption_closed = any(
                c.state in ('confirmed', 'done')
                and c.consumption_completeness == 'completo'
                for c in rec.consumption_ids
            )

    @api.onchange('production_line_id')
    def _onchange_production_line_clear_work_center(self):
        if self.work_center_id and self.production_line_id:
            if self.work_center_id.production_line_id != self.production_line_id:
                self.work_center_id = False
        elif not self.production_line_id:
            self.work_center_id = False

    @api.constrains('work_center_id', 'production_line_id')
    def _check_work_center_line(self):
        for rec in self:
            if not rec.work_center_id:
                continue
            if rec.work_center_id.production_line_id != rec.production_line_id:
                raise ValidationError(_(
                    'El centro de trabajo debe pertenecer a la línea de '
                    'producción del registro.'
                ))
            if rec.state == 'draft' and rec.work_center_id.state != 'active':
                raise ValidationError(_(
                    'El centro de trabajo "%s" no está activo.'
                ) % rec.work_center_id.display_name)

    @api.model
    def _kc_open_entry_states(self):
        """Estados que bloquean un segundo RP concurrente (no incluye done)."""
        return ('draft', 'confirmed')

    @api.model
    def _kc_sum_produced_qty_for_sol(self, sale_order_line, exclude_entry=None):
        """Suma qty de RP done no revertidos vinculados a la línea de OV."""
        if not sale_order_line:
            return 0.0
        domain = [
            ('sale_order_line_id', '=', sale_order_line.id),
            ('entry_id.state', '=', 'done'),
            ('entry_id.reversal_of_id', '=', False),
        ]
        if exclude_entry:
            domain.append(('entry_id', '!=', exclude_entry.id))
        lines = self.env['kc.production.entry.line'].search(domain)
        lines = lines.filtered(
            lambda l: not l.entry_id.reversed_by_id and not l.entry_id.is_reversal
        )
        return sum(lines.mapped('qty'))

    @api.depends('company_id', 'sale_order_id', 'production_line_id')
    def _compute_available_sale_order_ids(self):
        """OV disponibles: excluye solo las con RP en curso (draft/confirmed)."""
        Entry = self.env['kc.production.entry']
        for rec in self:
            disponibles = self.env['sale.order'].search([
                ('state', 'in', ['sale', 'done']),
            ])
            if rec.production_line_id:
                ocupadas = Entry.search([
                    ('sale_order_id', '!=', False),
                    ('production_line_id', '=', rec.production_line_id.id),
                    ('reversal_of_id', '=', False),
                    ('state', 'in', list(self._kc_open_entry_states())),
                ]).filtered(lambda e: not e.reversed_by_id).mapped('sale_order_id')
                disponibles = disponibles.filtered(
                    lambda so: so not in ocupadas
                    or so == rec.sale_order_id)
                disponibles = disponibles.filtered(
                    lambda so: rec._kc_sale_order_has_products_for_line(
                        so, rec.production_line_id))
            if rec.sale_order_id:
                disponibles |= rec.sale_order_id
            rec.available_sale_order_ids = disponibles

    @api.depends('company_id')
    def _compute_available_production_line_ids(self):
        Line = self.env['kc.production.line']
        for rec in self:
            rec.available_production_line_ids = Line.search(
                rec._kc_production_line_domain_for_user(rec.company_id))

    @api.depends('picking_id', 'picking_id.move_line_ids')
    def _compute_move_line_count(self):
        """Cuenta las operaciones de inventario (move lines) del albarán."""
        for rec in self:
            rec.move_line_count = len(rec.picking_id.move_line_ids) if rec.picking_id else 0

    @api.depends('sale_order_id', 'created_from_replenishment')
    def _compute_origin_type(self):
        """Determina el origen del RP: OV, Abastecimiento o Manual."""
        for rec in self:
            if rec.sale_order_id:
                rec.origin_type = 'sale_order'
            elif rec.created_from_replenishment:
                rec.origin_type = 'replenishment'
            else:
                rec.origin_type = 'manual'

    @api.depends(
        'line_ids.qty', 'line_ids.product_id',
        'consumption_ids.state',
        'consumption_ids.line_ids.line_type',
        'consumption_ids.line_ids.qty',
        'consumption_ids.line_ids.product_id',
        'consumption_ids.line_ids.service_value',
        'line_ids.kc_line_cost',
        'line_ids.kc_unit_cost',
        'line_ids.kc_technical_key',
    )
    def _compute_cost_comparison(self):
        """Compara el costo registrado del PT contra el consumo real (CMP done).

        El costo del PT es el asignado manualmente en cada línea del RP.
        """
        for rec in self:
            rec.registered_pt_cost = sum(
                line.kc_line_cost for line in rec.line_ids
            )
            costo_real = 0.0
            for cons in rec.consumption_ids.filtered(lambda c: c.state == 'done'):
                for line in cons.line_ids:
                    if line.line_type == 'service':
                        costo_real += line.service_value
                    else:
                        costo_real += line.qty * line.product_id.standard_price
            rec.real_consumption_cost = costo_real
            rec.cost_difference = costo_real - rec.registered_pt_cost

    @api.depends('line_ids.kc_cost_exceeds_sale', 'state')
    def _compute_kc_has_cost_above_sale(self):
        for rec in self:
            rec.kc_has_cost_above_sale = any(
                line.kc_cost_exceeds_sale for line in rec.line_ids
            )

    @api.depends('line_ids.kc_total_weight', 'line_ids.kc_total_area_sqft')
    def _compute_kc_entry_weight_area_totals(self):
        for rec in self:
            rec.kc_total_weight = sum(rec.line_ids.mapped('kc_total_weight'))
            rec.kc_total_area_sqft = sum(rec.line_ids.mapped('kc_total_area_sqft'))

    @api.depends('sale_order_id')
    def _compute_analytic_distribution(self):
        """Hereda la distribución analítica desde la Orden de Venta (no editable)."""
        for rec in self:
            rec.analytic_distribution = rec._kc_sale_analytic_distribution(rec.sale_order_id)

    @api.model
    def _kc_sale_analytic_distribution(self, sale_order):
        """Construye la distribución analítica a partir de una Orden de Venta.

        En esta instalación, sale.order NO tiene analytic_distribution directo:
        la analítica vive en el Proyecto (sale.order.project_id.account_id, una
        account.analytic.account). Prioridad:
          1) Cuenta analítica del Proyecto de la OV -> {id: 100}.
          2) Respaldo: primera línea de la OV con analytic_distribution propia.
        Devuelve False si no hay analítica (RP/CMP libre).
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

        Compatible con Odoo 18 (stock.move.stock_valuation_layer_ids ->
        account_move_id) y Odoo 19 (stock.move.account_move_id directo).
        """
        self.ensure_one()
        AccountMove = self.env['account.move']
        moves = AccountMove
        if not self.picking_id:
            return moves
        for sm in self.picking_id.move_ids:
            if 'account_move_id' in sm._fields and sm.account_move_id:
                moves |= sm.account_move_id
            if 'stock_valuation_layer_ids' in sm._fields:
                moves |= sm.stock_valuation_layer_ids.mapped('account_move_id')
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
            raise UserError(_("Este registro no tiene asientos contables asociados."))
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
        """True si este registro es a su vez una reversión de otro."""
        for rec in self:
            rec.is_reversal = bool(rec.reversal_of_id)

    def _compute_reversed_by_id(self):
        """Busca si existe un registro que revierte a este (sin almacenar)."""
        for rec in self:
            rec.reversed_by_id = self.search(
                [('reversal_of_id', '=', rec.id)], limit=1) if rec.id else False

    @api.model
    def _kc_sale_order_has_products_for_line(self, sale_order, production_line):
        """True si la OV tiene al menos un PT producible para la línea."""
        return bool(self._kc_filter_sale_lines_for_production(
            sale_order, production_line))

    @api.model
    def _kc_filter_sale_lines_for_production(self, sale_order, production_line=False):
        """Líneas de OV elegibles para RP: técnicos con clave o producción simple."""
        if not sale_order:
            return self.env['sale.order.line']
        Plan = self.env['kc.production.plan.line']
        lines = sale_order.order_line.filtered(
            lambda l: not l.display_type
            and l.product_id
            and l.product_id.tracking == 'lot'
            and Plan._kc_sol_is_plannable(l)
        )
        if not production_line:
            return lines
        Line = self.env['kc.production.line']
        return lines.filtered(
            lambda l: Line.resolve_for_product(
                l.product_id, company=sale_order.company_id) == production_line
        )

    @api.model
    def _kc_description_from_sale_line(self, ov_line, lot=False):
        """Texto para Especificaciones del RP desde la línea de OV.

        Prioridad:
        1) technical_description (matriz técnica)
        2) technical_description del lote
        3) descripción libre de la OV (name), sin el prefijo del producto
           — caso PT general tipo GENROTULOS.
        """
        if not ov_line:
            return False
        desc = getattr(ov_line, 'technical_description', False) or False
        if not desc and lot:
            desc = getattr(lot, 'technical_description', False) or False
        if desc:
            return desc
        raw = (ov_line.name or '').strip()
        if not raw:
            return False
        product = ov_line.product_id
        prefixes = []
        if product:
            if product.display_name:
                prefixes.append(product.display_name.strip())
            if product.name:
                prefixes.append(product.name.strip())
            code = product.default_code
            if code:
                prefixes.append('[%s]' % code)
                prefixes.append('[%s] %s' % (code, product.name or ''))
        cleaned = raw
        for prefix in prefixes:
            if not prefix:
                continue
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].lstrip(' \t\r\n:-–—')
                break
            # Prefijo en la primera línea (nombre producto + salto + detalle).
            first_line, *rest = cleaned.splitlines()
            if first_line.strip() == prefix and rest:
                cleaned = '\n'.join(rest).strip()
                break
        cleaned = cleaned.strip()
        if not cleaned or cleaned == raw:
            # Si quedó igual al display_name del producto, no aporta valor.
            if product and cleaned in {
                (product.display_name or '').strip(),
                (product.name or '').strip(),
            }:
                return False
            return cleaned or False
        return cleaned

    def _kc_entry_line_vals_from_sale_line(self, ov_line):
        """Valores de línea RP a partir de una línea de OV (specs y cantidad a producir)."""
        self.ensure_one()
        Lot = self.env['stock.lot']
        technical_key = getattr(ov_line, 'technical_key', False) or False
        technical_desc = self._kc_description_from_sale_line(ov_line)
        ov_qty = ov_line.product_uom_qty
        stock_qty = 0.0
        if technical_key and hasattr(ov_line, '_kc_get_compatible_available_qty'):
            stock_qty = ov_line._kc_get_compatible_available_qty(
                warehouse=self.warehouse_id,
            )
        elif hasattr(ov_line, '_kc_get_compatible_available_qty'):
            stock_qty = ov_line._kc_get_compatible_available_qty(
                warehouse=self.warehouse_id,
            )
        produced_qty = self._kc_sum_produced_qty_for_sol(ov_line, exclude_entry=self)
        qty_to_produce = max(0.0, ov_qty - stock_qty - produced_qty)
        unit_weight, unit_area = self.env[
            'product.technical.configuration'
        ]._kc_resolve_weight_area(ov_line.product_id, technical_key)
        return {
            'product_id': ov_line.product_id.id,
            'qty': qty_to_produce,
            'kc_ov_qty': ov_qty,
            'kc_stock_qty': stock_qty,
            'kc_produced_qty': produced_qty,
            'kc_qty_to_produce': qty_to_produce,
            'uom_id': ov_line.product_uom.id,
            'sale_order_line_id': ov_line.id,
            'lot_id': False,
            'kc_technical_key': technical_key,
            'kc_technical_description': technical_desc,
            'kc_unit_weight': unit_weight,
            'kc_unit_area_sqft': unit_area,
            'kc_unit_cost': Lot._kc_resolve_unit_cost(
                ov_line.product_id,
                technical_key=technical_key,
                lot=False,
                company=self.company_id,
            ),
        }

    def _kc_build_entry_lines_from_sale(self):
        """Construye comandos (0,0,vals) de PT desde la OV para esta línea."""
        self.ensure_one()
        commands = []
        if not self.sale_order_id or not self.production_line_id:
            return commands
        ov_lines = self._kc_filter_sale_lines_for_production(
            self.sale_order_id, self.production_line_id)
        for ov_line in ov_lines:
            commands.append((0, 0, self._kc_entry_line_vals_from_sale_line(ov_line)))
        return commands

    def _kc_pending_production_lines_message(self):
        """Texto informativo sobre otras líneas pendientes en la misma OV."""
        self.ensure_one()
        if not self.sale_order_id:
            return False
        groups, unassigned = self.sale_order_id._kc_group_order_lines_by_production_line()
        pending = []
        for prod_line, ov_lines in groups.items():
            if prod_line == self.production_line_id:
                continue
            open_entry = self.sale_order_id._kc_get_open_entry_for_line(prod_line)
            remaining = self.sale_order_id._kc_line_remaining_qty(prod_line)
            if remaining <= 0 and not open_entry:
                continue
            if open_entry:
                state_txt = open_entry.state
            elif remaining > 0:
                state_txt = _('parcial / pendiente')
            else:
                state_txt = _('sin RP')
            pending.append('%s (%s)' % (prod_line.name, state_txt))
        parts = []
        if pending:
            parts.append(_(
                'Otras líneas de producción en esta OV: %s',
                ', '.join(pending),
            ))
        if unassigned:
            parts.append(_(
                'Productos sin línea de producción configurada: %s',
                ', '.join(unassigned.mapped('product_id.display_name')),
            ))
        return '\n'.join(parts) if parts else False

    def _kc_build_entry_lines_from_plan(self):
        """Una sola línea PT desde el bloque de plan (no toda la OV)."""
        self.ensure_one()
        plan = self.plan_line_id
        if not plan or not plan.product_id:
            return []
        if plan.sale_order_line_id:
            vals = self._kc_entry_line_vals_from_sale_line(plan.sale_order_line_id)
        else:
            vals = {
                'product_id': plan.product_id.id,
                'uom_id': plan.product_id.uom_id.id,
                'sale_order_line_id': False,
            }
        qty = plan._kc_qty_for_new_rp()
        vals.update({
            'qty': qty,
            'kc_qty_to_produce': qty,
            'kc_technical_key': plan.technical_key or vals.get('kc_technical_key') or False,
            'kc_technical_description': (
                plan.technical_description
                or vals.get('kc_technical_description')
                or False
            ),
        })
        return [(0, 0, vals)]

    @api.onchange('sale_order_id', 'production_line_id', 'plan_line_id')
    def _onchange_sale_order_production(self):
        """Carga PT de la OV para la línea; si hay plan, solo esa línea OV."""
        if not self.sale_order_id and not self.plan_line_id:
            self.line_ids = [(5, 0, 0)]
            return

        # Desde plan: nunca cargar todas las líneas de la OV.
        if self.plan_line_id:
            lines_cmds = self._kc_build_entry_lines_from_plan()
            self.line_ids = [(5, 0, 0)] + lines_cmds
            for line in self.line_ids:
                if line.sale_order_line_id:
                    line._kc_apply_sale_line_specs(line.sale_order_line_id)
            return

        if not self.sale_order_id:
            return
        if not self.production_line_id:
            return

        conflicto = self._get_conflicting_entry()
        if conflicto:
            estados = dict(self._fields['state'].selection)
            return {
                'warning': {
                    'title': _('Registro de Producción en curso'),
                    'message': _(
                        'La Orden de Venta %(so)s ya tiene un Registro de '
                        'Producción en curso para %(line)s: %(rp)s '
                        '(estado: %(estado)s). Finalícelo o cancelelo antes '
                        'de crear otro.',
                        so=self.sale_order_id.name,
                        line=self.production_line_id.name,
                        rp=conflicto.name,
                        estado=estados.get(conflicto.state, conflicto.state),
                    ),
                }
            }

        lines_cmds = self._kc_build_entry_lines_from_sale()
        self.line_ids = [(5, 0, 0)] + lines_cmds
        # Aplicar lote/especificaciones en el cliente para cada línea vinculada.
        for line in self.line_ids:
            if line.sale_order_line_id:
                line._kc_apply_sale_line_specs(line.sale_order_line_id)

        if not lines_cmds:
            return {
                'warning': {
                    'title': _('Sin productos para esta línea'),
                    'message': _(
                        'La Orden de Venta %(so)s no tiene productos terminados '
                        '(rastreo por lote) asignables a la línea %(line)s. '
                        'Revise las categorías de producto o la configuración '
                        'de líneas de producción.',
                        so=self.sale_order_id.name,
                        line=self.production_line_id.name,
                    ),
                }
            }

        info = self._kc_pending_production_lines_message()
        if info:
            return {
                'warning': {
                    'title': _('Otras líneas de producción en esta OV'),
                    'message': info,
                }
            }

    def _get_conflicting_entry(self):
        """Otro RP en curso (draft/confirmed) para la misma OV y línea."""
        self.ensure_one()
        if not self.sale_order_id or not self.production_line_id:
            return self.browse()
        otros = self.search([
            ('id', '!=', self._origin.id or 0),
            ('sale_order_id', '=', self.sale_order_id.id),
            ('production_line_id', '=', self.production_line_id.id),
            ('reversal_of_id', '=', False),
            ('state', 'in', list(self._kc_open_entry_states())),
        ])
        otros = otros.filtered(lambda e: not e.reversed_by_id)
        return otros[:1]

    @api.constrains('sale_order_id', 'production_line_id', 'state')
    def _check_unique_sale_order_line(self):
        """Como máximo un RP en curso (draft/confirmed) por OV + línea."""
        estados = dict(self._fields['state'].selection)
        for rec in self:
            if rec.is_reversal or not rec.sale_order_id or not rec.production_line_id:
                continue
            if rec.state == 'cancel':
                continue
            if rec.state not in self._kc_open_entry_states():
                continue
            conflicto = rec._get_conflicting_entry()
            if conflicto:
                raise ValidationError(_(
                    'La Orden de Venta %(so)s ya tiene un Registro de Producción '
                    'en curso para la línea %(line)s: %(rp)s (estado: %(estado)s).',
                    so=rec.sale_order_id.name,
                    line=rec.production_line_id.name,
                    rp=conflicto.name,
                    estado=estados.get(conflicto.state, conflicto.state),
                ))

    def _kc_assert_remaining_qty(self):
        """Bloquea si no queda saldo pendiente por producir en la OV+línea."""
        self.ensure_one()
        if not self.sale_order_id or not self.production_line_id:
            return
        remaining_total = 0.0
        for line in self.line_ids:
            if not line.sale_order_line_id:
                remaining_total += line.qty
                continue
            remaining_total += line.kc_ov_qty_remaining
        if remaining_total <= 0 and self.line_ids:
            # Permitir si el operador aún está editando cantidades a 0 en borrador
            # pero al confirmar no debe quedar todo en cero con OV vinculada.
            pass

    def _kc_sync_plan_line_state(self, event):
        """Sincroniza el bloque de planificación vinculado (única fuente)."""
        for rec in self:
            plan = rec.plan_line_id
            if not plan:
                plan = self.env['kc.production.plan.line'].search([
                    ('entry_id', '=', rec.id),
                ], limit=1)
            if plan:
                plan._kc_sync_from_entry(rec, event)

    def _kc_sync_all_lines_from_sale_order(self):
        """Sincroniza todas las líneas del RP con la OV sin duplicar emparejamientos."""
        self.ensure_one()
        if not self.sale_order_id:
            return
        used_sol_ids = set()
        for line in self.line_ids.sorted('id'):
            sol_id = line.with_context(kc_skip_specs_sync=True)._kc_ensure_sale_line_link(
                exclude_sol_ids=used_sol_ids,
            )
            if sol_id:
                used_sol_ids.add(sol_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('production_line_id'):
                line_id = self._default_production_line_id()
                if not line_id:
                    line_id = self._kc_resolve_production_line_id_from_vals(vals)
                if line_id:
                    vals['production_line_id'] = line_id
        records = super().create(vals_list)
        for rec in records:
            if rec.plan_line_id and not rec.plan_line_id.entry_id:
                rec.plan_line_id.entry_id = rec.id
            if (rec.sale_order_id and rec.production_line_id
                    and not rec.line_ids and rec.state == 'draft'
                    and not rec.plan_line_id):
                line_cmds = rec._kc_build_entry_lines_from_sale()
                if line_cmds:
                    rec.with_context(kc_skip_entry_specs_sync=True).write(
                        {'line_ids': line_cmds})
            # Desde plan: asegurar solo la línea del bloque; no resincronizar toda la OV.
            # Respetar cantidad ya cargada (parciales); solo completar si viene en 0.
            if rec.plan_line_id and rec.state == 'draft':
                plan = rec.plan_line_id
                if not rec.line_ids:
                    cmds = rec._kc_build_entry_lines_from_plan()
                    if cmds:
                        rec.with_context(kc_skip_entry_specs_sync=True).write(
                            {'line_ids': cmds})
                elif plan.sale_order_line_id:
                    extras = rec.line_ids.filtered(
                        lambda l: l.sale_order_line_id
                        and l.sale_order_line_id != plan.sale_order_line_id
                    )
                    if extras:
                        extras.with_context(kc_allow_plan_line_unlink=True).unlink()
                target = rec.line_ids
                if plan.sale_order_line_id:
                    target = rec.line_ids.filtered(
                        lambda l: l.sale_order_line_id == plan.sale_order_line_id
                    ) or rec.line_ids[:1]
                if target:
                    rem = plan._kc_qty_for_new_rp()
                    rounding = self.env['decimal.precision'].precision_get(
                        'Product Unit of Measure')
                    for line in target:
                        write_vals = {
                            'kc_technical_key': plan.technical_key or False,
                            'kc_technical_description': (
                                plan.technical_description or False
                            ),
                        }
                        if float_is_zero(line.qty, precision_rounding=rounding):
                            write_vals['qty'] = rem
                            write_vals['kc_qty_to_produce'] = rem
                        line.write(write_vals)
            elif rec.sale_order_id and rec.line_ids and rec.state == 'draft':
                rec._kc_sync_all_lines_from_sale_order()
        return records

    def _kc_assert_no_plan_line_add_remove(self, commands):
        """RP desde plan: no permitir crear/borrar líneas (solo editar qty)."""
        if not commands:
            return
        for rec in self:
            if not rec.plan_line_id:
                continue
            for cmd in commands:
                if not cmd:
                    continue
                op = cmd[0]
                if op in (0, 2, 3, 5):
                    raise UserError(_(
                        'Este RP proviene del plan "%(plan)s". No se pueden '
                        'agregar ni eliminar líneas del detalle: ajuste solo '
                        'la cantidad a producir (puede ser parcial).',
                        plan=rec.plan_line_id.display_name,
                    ))

    def write(self, vals):
        if 'line_ids' in vals:
            self._kc_assert_no_plan_line_add_remove(vals.get('line_ids'))
        res = super().write(vals)
        if self.env.context.get('kc_skip_entry_specs_sync'):
            return res
        if vals.get('sale_order_id') or vals.get('production_line_id') or vals.get('line_ids'):
            for rec in self.filtered(
                lambda r: r.sale_order_id and r.state == 'draft' and not r.plan_line_id
            ):
                rec._kc_sync_all_lines_from_sale_order()
        return res

    def _kc_user_can_plan_or_produce_rp(self):
        """Planificador u operador: crear/editar RP en borrador (sin confirmar)."""
        user = self.env.user
        return (
            user.has_group('kc_manual_production.kc_production_group_planner')
            or user.has_group('kc_manual_production.kc_production_group_user')
            or user.has_group('kc_manual_production.kc_production_group_manager')
            or user.has_group('stock.group_stock_manager')
        )

    def _kc_user_can_confirm_rp(self):
        """Producción (o gerente / stock manager) confirma el RP — no planificador solo."""
        user = self.env.user
        return (
            user.has_group('kc_manual_production.kc_production_group_user')
            or user.has_group('kc_manual_production.kc_production_group_manager')
            or user.has_group('stock.group_stock_manager')
        )

    def _kc_user_can_validate_rp(self):
        """Inventario / bodega (o gerente / stock manager) recibe el PT."""
        user = self.env.user
        return (
            user.has_group('kc_manual_production.kc_production_group_bodega')
            or user.has_group('kc_manual_production.kc_production_group_manager')
            or user.has_group('stock.group_stock_manager')
        )

    def action_confirm(self):
        """Confirma el RP: asigna referencia, resuelve lotes y pasa a 'confirmed'."""
        if not self._kc_user_can_confirm_rp():
            raise UserError(_(
                'Solo producción puede confirmar un Registro de Producción. '
                'Inventario recibe el producto con Validar.'
            ))
        rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Debe agregar al menos una línea de producto terminado antes de confirmar."))
            # RP desde plan: ficha técnica obligatoria; qty parcial <= saldo del plan.
            if rec.plan_line_id:
                plan = rec.plan_line_id
                tech_key = (plan.technical_key or '').strip()
                Plan = self.env['kc.production.plan.line']
                is_simple = Plan._kc_product_is_simple_production(plan.product_id)
                if not tech_key and not is_simple:
                    raise UserError(_(
                        'El bloque de planificación %(plan)s no tiene clave '
                        'técnica. No se puede confirmar un RP sin ficha técnica.',
                        plan=plan.display_name,
                    ))
                remaining = plan._kc_qty_for_new_rp()
                for line in rec.line_ids:
                    if float_is_zero(line.qty, precision_rounding=rounding):
                        continue
                    if float_compare(line.qty, remaining, precision_rounding=rounding) > 0:
                        raise UserError(_(
                            'La cantidad de %(product)s (%(qty)s) supera el saldo '
                            'pendiente del plan (%(rem)s = planificado − ya en PT).',
                            product=line.product_id.display_name,
                            qty=line.qty,
                            rem=remaining,
                        ))
                    if tech_key and not (line.kc_technical_key or '').strip():
                        line.kc_technical_key = tech_key
                    if not line.kc_technical_description and plan.technical_description:
                        line.kc_technical_description = plan.technical_description
                    if line.sale_order_line_id:
                        max_prod = self.env['kc.production.plan.line']._kc_pending_qty_for_sol(
                            line.sale_order_line_id)
                        if float_compare(line.qty, max_prod, precision_rounding=rounding) > 0:
                            raise UserError(_(
                                'La cantidad (%(qty)s) supera lo pendiente de '
                                'producir en la OV (%(rem)s = OV − fabricado).',
                                qty=line.qty,
                                rem=max_prod,
                            ))
            elif rec.sale_order_id:
                positive = rec.line_ids.filtered(
                    lambda l: not float_is_zero(l.qty, precision_rounding=rounding)
                )
                if not positive:
                    raise UserError(_(
                        'No hay cantidad a producir. El saldo pendiente de la '
                        'Orden de Venta ya está cubierto por stock o RP validados.'
                    ))
                for line in positive:
                    if line.sale_order_line_id and line.qty > line.kc_ov_qty_remaining + 1e-6:
                        raise UserError(_(
                            'La cantidad de %(product)s (%(qty)s) supera el saldo '
                            'pendiente (%(rem)s).',
                            product=line.product_id.display_name,
                            qty=line.qty,
                            rem=line.kc_ov_qty_remaining,
                        ))
            if rec.name == '/' or not rec.name:
                rec.name = self.env['ir.sequence'].next_by_code('kc.production.entry') or '/'
            if not rec.plan_line_id:
                rec._kc_sync_all_lines_from_sale_order()
            else:
                # Specs sí; no resetear qty parcial del usuario.
                plan = rec.plan_line_id
                tech_key = (plan.technical_key or '').strip()
                remaining = plan._kc_qty_for_new_rp()
                for line in rec.line_ids:
                    if float_is_zero(line.qty, precision_rounding=rounding):
                        continue
                    if float_compare(line.qty, remaining, precision_rounding=rounding) > 0:
                        raise UserError(_(
                            'La cantidad de %(product)s (%(qty)s) supera el saldo '
                            'pendiente del plan (%(rem)s).',
                            product=line.product_id.display_name,
                            qty=line.qty,
                            rem=remaining,
                        ))
                    if tech_key and not (line.kc_technical_key or '').strip():
                        line.kc_technical_key = tech_key
                    if not line.kc_technical_description and plan.technical_description:
                        line.kc_technical_description = plan.technical_description
            for line in rec.line_ids:
                line._kc_refresh_weight_area_from_matrix()
                if float_is_zero(line.qty, precision_rounding=rounding):
                    line.lot_id = False
                    continue
                # Costo obligatorio antes de crear/asignar lote (nunca lote a 0).
                if not line.kc_unit_cost:
                    line.kc_unit_cost = line._kc_get_suggested_unit_cost()
                digits = line._kc_get_price_digits()
                if float_compare(line.kc_unit_cost or 0.0, 0.0, precision_digits=digits) <= 0:
                    raise UserError(_(
                        'Debe indicar un costo unitario mayor a cero para '
                        '"%(product)s" antes de confirmar. El lote no puede '
                        'crearse sin costo.',
                        product=line.product_id.display_name,
                    ))
                lote = line._resolve_or_create_lot()
                if line.lot_id != lote:
                    line.lot_id = lote.id
                line._kc_refresh_technical_description()
                # Valorizar el lote con el costo del RP al confirmar (no dejar 0/matriz sola).
                if line.lot_id and line.product_id.lot_valuated:
                    line.lot_id.with_company(rec.company_id).standard_price = line.kc_unit_cost
            rec.state = 'confirmed'
            rec._kc_sync_plan_line_state('confirm')
        return True

    def _get_warehouse(self):
        """Devuelve el almacén de la compañía del registro (o lanza error)."""
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
        """Crea y valida un stock.picking con las líneas del registro.

        Reutilizado tanto por la validación normal (entrada) como por la
        reversión (salida en sentido inverso). Usa el lote de cada línea.
        """
        self.ensure_one()
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': location_src.id,
            'location_dest_id': location_dest.id,
            'origin': self.name,
            'partner_id': self.partner_id.id or False,
            'company_id': self.company_id.id,
        })
        for line in self.line_ids:
            if float_is_zero(line.qty, precision_rounding=self.env['decimal.precision'].precision_get('Product Unit of Measure')):
                continue
            if not line.lot_id:
                raise UserError(_("La línea del producto %s no tiene lote asignado.") % line.product_id.display_name)
            move = self.env['stock.move'].create({
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'product_uom': line.uom_id.id,
                'price_unit': line.kc_unit_cost or 0.0,
                'picking_id': picking.id,
                'location_id': location_src.id,
                'location_dest_id': location_dest.id,
                'company_id': self.company_id.id,
                # Traza el origen para propagar la analítica del RP al asiento.
                'kc_production_entry_id': self.id,
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
        # Validamos saltando el asistente de backorder (cantidad completa).
        result = picking.with_context(skip_backorder=True).button_validate()
        # button_validate puede devolver una acción (asistente). Si es la
        # confirmación de backorder, la procesamos SIN crear backorder para que
        # el movimiento quede realmente hecho.
        if isinstance(result, dict) and result.get('res_model') == 'stock.backorder.confirmation':
            wizard = self.env['stock.backorder.confirmation'].with_context(
                result.get('context', {})).create({})
            wizard.process_cancel_backorder()
        # Guarda de integridad: si el albarán no quedó 'done', el inventario NO
        # se movió; abortamos para no marcar el RP como validado en falso.
        if picking.state != 'done':
            raise UserError(_(
                "No se pudo completar el movimiento de inventario "
                "(albarán %(name)s, estado %(state)s). Revise stock y ubicaciones.",
                name=picking.name, state=picking.state))
        return picking

    def _kc_validate_cost_vs_sale(self):
        """Bloquea la validación si el costo supera el precio neto de la OV."""
        self.ensure_one()
        errors = []
        for line in self.line_ids:
            if not line._find_sale_order_line():
                continue
            if line.kc_cost_exceeds_sale:
                errors.append(_(
                    '%(product)s: costo %(cost).2f > precio venta OV %(price).2f',
                    product=line.product_id.display_name,
                    cost=line.kc_unit_cost,
                    price=line.kc_sale_unit_price,
                ))
        if errors:
            raise UserError(_(
                'No se puede validar el registro: el costo unitario supera el '
                'precio de venta de la Orden de Venta en las siguientes líneas:\n'
                '%(lines)s\n\n'
                'Corrija el costo unitario antes de validar.',
                lines='\n'.join(errors),
            ))

    def action_validate(self):
        """Valida el RP creando un picking de ENTRADA (Producción → Stock)."""
        if not self._kc_user_can_validate_rp():
            raise UserError(_(
                'Solo inventario (bodega) puede validar un RP y recibir el '
                'producto terminado al stock.'
            ))
        rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(_("Solo se pueden validar registros en estado 'Confirmado'."))
            if not rec.line_ids:
                raise UserError(_("No hay líneas de producto terminado para validar."))
            lines_to_move = rec.line_ids.filtered(
                lambda l: not float_is_zero(l.qty, precision_rounding=rounding)
            )
            if not lines_to_move:
                rec.state = 'done'
                rec._kc_sync_plan_line_state('validate')
                continue
            rec._kc_validate_cost_vs_sale()
            for line in lines_to_move:
                line._kc_apply_lot_unit_cost()

            location_src = rec._get_production_location()
            location_dest = rec._kc_get_rp_destination_location()
            picking_type = rec.picking_type_id or rec._get_picking_type('rp', 'incoming')

            picking = rec._create_stock_picking(location_src, location_dest, picking_type)
            rec.picking_id = picking.id
            rec.state = 'done'
            rec._kc_sync_plan_line_state('validate')
        return True

    def action_open_reversal_wizard(self):
        """Abre el wizard de confirmación de reversión con el RP precargado."""
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_("Solo se pueden revertir registros validados."))
        if self.is_reversal:
            raise UserError(_("Una reversión no puede revertirse de nuevo."))
        if self.reversed_by_id:
            raise UserError(_("Este registro ya fue revertido por %s.") % self.reversed_by_id.name)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Revertir Registro de Producción'),
            'res_model': 'kc.production.entry.reversal.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_entry_id': self.id},
        }

    def create_reversal(self, reason):
        """Crea un RP de reversión en estado 'done' con picking inverso.

        El picking de reversión va Stock → Producción (sentido contrario al de
        la entrada original), usando el MISMO lote para conservar el historial.
        """
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_("Solo se pueden revertir registros validados."))
        if self.is_reversal:
            raise UserError(_("Una reversión no puede revertirse de nuevo."))
        if self.reversed_by_id:
            raise UserError(_("Este registro ya fue revertido por %s.") % self.reversed_by_id.name)

        reversal = self.create({
            'reversal_of_id': self.id,
            'notes_reversal': reason,
            'sale_order_id': self.sale_order_id.id or False,
            'partner_id': self.partner_id.id or False,
            'company_id': self.company_id.id,
            'warehouse_id': self.warehouse_id.id or False,
            'production_line_id': self.production_line_id.id,
            'date_production': fields.Datetime.now(),
            'line_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'qty': line.qty,
                'uom_id': line.uom_id.id,
                'lot_id': line.lot_id.id,
                'kc_unit_cost': line.kc_unit_cost,
                'kc_unit_weight': line.kc_unit_weight,
                'kc_unit_area_sqft': line.kc_unit_area_sqft,
                'kc_technical_key': line.kc_technical_key,
            }) for line in self.line_ids],
        })
        reversal.name = self.env['ir.sequence'].next_by_code('kc.production.entry') or '/'

        # Picking inverso: Stock → Producción (usa el tipo CMP, misma dirección).
        location_src = reversal._kc_get_rp_destination_location()
        location_dest = reversal._get_production_location()
        picking_type = reversal._get_picking_type('cmp', 'outgoing')

        picking = reversal._create_stock_picking(location_src, location_dest, picking_type)
        reversal.picking_id = picking.id
        reversal.state = 'done'
        reversal.message_post(body=_("Reversión del registro %s. Motivo: %s") % (self.name, reason))
        self.message_post(body=_("Registro revertido por %s.") % reversal.name)
        return reversal

    def action_cancel(self):
        """Cancela el RP. No permitido si ya fue validado (state='done')."""
        for rec in self:
            if rec.state == 'done':
                raise UserError(_("No se puede cancelar un registro ya validado."))
            if rec.state == 'draft':
                if not self._kc_user_can_plan_or_produce_rp():
                    raise UserError(_(
                        'No tiene permiso para cancelar un RP en borrador.'
                    ))
            elif not self._kc_user_can_confirm_rp():
                raise UserError(_(
                    'Solo producción puede cancelar un RP confirmado.'
                ))
            rec.state = 'cancel'
        return True

    def action_draft(self):
        """Regresa un registro cancelado a borrador."""
        if not self._kc_user_can_plan_or_produce_rp():
            raise UserError(_(
                'Solo planificador o producción pueden volver un RP a borrador.'
            ))
        for rec in self:
            if rec.state == 'cancel':
                rec.state = 'draft'
        return True

    def action_view_picking(self):
        """Abre el albarán de entrada relacionado (botón inteligente)."""
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_("Este registro aún no tiene un albarán generado."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Albarán de Entrada'),
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.picking_id.id,
            'target': 'current',
        }

    def action_view_sale_order(self):
        """Botón inteligente: abre la Orden de Venta vinculada."""
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_("Este registro no está vinculado a una Orden de Venta."))
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
            raise UserError(_("Este registro aún no tiene movimientos de inventario."))
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

    def action_view_consumptions(self):
        """Botón inteligente: abre los consumos de MP vinculados a este RP."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consumos de Materia Prima'),
            'res_model': 'kc.production.consumption',
            'view_mode': 'list,form',
            'domain': [('entry_id', '=', self.id)],
            'context': {'default_entry_id': self.id},
        }


class KcProductionEntryLine(models.Model):
    """Línea de Registro de Producción: un producto terminado con su lote."""
    _name = 'kc.production.entry.line'
    _description = 'Línea de Registro de Producción'

    entry_id = fields.Many2one(
        comodel_name='kc.production.entry',
        string='Registro de Producción',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Producto Terminado',
        required=True,
        domain="[('sale_ok', '=', True), ('tracking', '=', 'lot')]",
        help="Producto Terminado vendible, rastreado por lote.",
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
    lot_id = fields.Many2one(
        comodel_name='stock.lot',
        string='Lote',
        readonly=True,
        copy=False,
        help="Se hereda de la línea de la Orden de Venta si ya tiene lote; "
             "en caso contrario se genera al confirmar el Registro de Producción.",
    )
    sale_order_line_id = fields.Many2one(
        comodel_name='sale.order.line',
        string='Línea de Orden de Venta',
        readonly=True,
        copy=False,
        help="Línea de venta de origen, usada para heredar/crear el lote correcto.",
    )
    kc_technical_key = fields.Char(
        string='Clave Técnica',
        readonly=True,
        copy=False,
        help="Especificación técnica (matriz) a producir cuando el RP nace de "
             "una regla de abastecimiento, sin Orden de Venta. El lote se crea "
             "desde la configuración técnica del producto con esta clave.",
    )
    kc_technical_description = fields.Text(
        string='Especificaciones',
        readonly=True,
        copy=False,
        help="Descripción legible de la especificación técnica a producir.",
    )
    kc_unit_cost = fields.Float(
        string='Costo unitario',
        digits='Product Price',
        help="Costo asignado en producción. Se aplica al lote al validar el RP.",
    )
    kc_sale_unit_price = fields.Float(
        string='Precio venta OV',
        compute='_compute_sale_cost_check',
        digits='Product Price',
        help="Precio neto unitario de la línea de venta (referencia interna).",
    )
    kc_cost_exceeds_sale = fields.Boolean(
        string='Costo supera venta',
        compute='_compute_sale_cost_check',
    )
    kc_line_cost = fields.Monetary(
        string='Costo línea',
        compute='_compute_kc_line_cost',
        currency_field='currency_id',
        help="Cantidad x costo unitario asignado en el RP.",
    )
    currency_id = fields.Many2one(
        related='entry_id.currency_id',
        readonly=True,
    )
    kc_ov_qty = fields.Float(
        string='Cantidad OV',
        digits='Product Unit of Measure',
        readonly=True,
    )
    kc_stock_qty = fields.Float(
        string='Stock compatible',
        digits='Product Unit of Measure',
        readonly=True,
    )
    kc_produced_qty = fields.Float(
        string='Ya producido',
        digits='Product Unit of Measure',
        readonly=True,
        help='Cantidad ya validada en otros RP done no revertidos de esta línea OV.',
    )
    kc_ov_qty_remaining = fields.Float(
        string='Saldo pendiente',
        compute='_compute_kc_ov_qty_remaining',
        digits='Product Unit of Measure',
        help='ov_qty − stock compatible − ya producido (sin contar este RP).',
    )
    kc_qty_to_produce = fields.Float(
        string='A producir',
        digits='Product Unit of Measure',
        default=0.0,
    )
    kc_unit_weight = fields.Float(
        string='Peso unitario (kg)',
        digits='Stock Weight',
        readonly=True,
        copy=False,
        default=0.0,
        help='Peso unitario desde la matriz técnica. 0 si no está definido.',
    )
    kc_unit_area_sqft = fields.Float(
        string='Área unitaria (FT²)',
        digits=(16, 4),
        readonly=True,
        copy=False,
        default=0.0,
        help='Área unitaria (FT²) desde la matriz técnica. 0 si no está definida.',
    )
    kc_total_weight = fields.Float(
        string='Peso total (kg)',
        compute='_compute_kc_weight_area_totals',
        digits='Stock Weight',
        help='Peso unitario × cantidad a producir.',
    )
    kc_total_area_sqft = fields.Float(
        string='Área total (FT²)',
        compute='_compute_kc_weight_area_totals',
        digits=(16, 4),
        help='Área unitaria (FT²) × cantidad a producir.',
    )

    @api.depends('qty', 'kc_unit_weight', 'kc_unit_area_sqft')
    def _compute_kc_weight_area_totals(self):
        for line in self:
            line.kc_total_weight = (line.qty or 0.0) * (line.kc_unit_weight or 0.0)
            line.kc_total_area_sqft = (line.qty or 0.0) * (line.kc_unit_area_sqft or 0.0)

    def _kc_resolve_unit_weight_area(self, product=None, technical_key=None):
        """Resuelve peso/área unitarios desde matriz; 0 si no hay config."""
        self.ensure_one()
        product = product or self.product_id
        technical_key = technical_key if technical_key is not None else self.kc_technical_key
        if not product or not technical_key:
            return 0.0, 0.0
        Configuration = self.env['product.technical.configuration']
        if not hasattr(Configuration, '_kc_resolve_weight_area'):
            return 0.0, 0.0
        return Configuration._kc_resolve_weight_area(product, technical_key)

    def _kc_refresh_weight_area_from_matrix(self):
        """Actualiza unitarios desde la matriz técnica (readonly en UI)."""
        for line in self:
            weight, area = line._kc_resolve_unit_weight_area()
            vals = {}
            if line.kc_unit_weight != weight:
                vals['kc_unit_weight'] = weight
            if line.kc_unit_area_sqft != area:
                vals['kc_unit_area_sqft'] = area
            if vals:
                if line.id:
                    line.with_context(kc_skip_specs_sync=True).write(vals)
                else:
                    line.kc_unit_weight = weight
                    line.kc_unit_area_sqft = area

    @api.model
    def _kc_get_lot_from_sale_line(self, sale_line):
        """Devuelve el lote ya creado para una línea de OV.

        Prioridad: lot_id en la línea → lote por sale_order_line_id →
        producto + clave técnica + pedido.
        """
        Lot = self.env['stock.lot']
        if not sale_line:
            return Lot
        if sale_line.lot_id:
            return sale_line.lot_id
        lot = Lot.search([('sale_order_line_id', '=', sale_line.id)], limit=1)
        if lot:
            return lot
        tech_key = getattr(sale_line, 'technical_key', False)
        if tech_key and sale_line.order_id:
            order_id = sale_line.order_id.id
            lot = Lot.search([
                ('product_id', '=', sale_line.product_id.id),
                ('technical_key', '=', tech_key),
                '|',
                ('sale_order_id', '=', order_id),
                ('kc_sale_order_id', '=', order_id),
            ], limit=1)
            if lot:
                return lot
        return Lot

    def _kc_is_rp_lot_for_this_order(self, lot):
        """True si el lote pertenece a la misma OV y no es lote de inventario.

        Acepta lotes de venta/producción aunque aún no tengan kc_entry_id
        (p. ej. creados en un intento previo de confirmación sin stock).
        """
        self.ensure_one()
        if not lot:
            return False
        if getattr(lot, 'source_type', False) == 'inventory':
            return False
        entry = self.entry_id
        if not entry.sale_order_id:
            return bool(getattr(lot, 'kc_entry_id', False))
        order = entry.sale_order_id
        if getattr(lot, 'kc_sale_order_id', False) and lot.kc_sale_order_id == order:
            return True
        if getattr(lot, 'sale_order_id', False) and lot.sale_order_id == order:
            return True
        return False

    def _kc_get_rp_lot_from_sale_line(self, sale_line):
        """Lote de producción de esta OV vinculado a la línea (no inventario)."""
        Lot = self.env['stock.lot']
        if not sale_line:
            return Lot
        if sale_line.lot_id and self._kc_is_rp_lot_for_this_order(sale_line.lot_id):
            return sale_line.lot_id
        order_id = sale_line.order_id.id
        tech_key = sale_line.technical_key
        if not tech_key:
            return Lot
        return Lot.search([
            ('product_id', '=', sale_line.product_id.id),
            ('technical_key', '=', sale_line.technical_key),
            ('source_type', '!=', 'inventory'),
            '|',
            ('kc_sale_order_id', '=', order_id),
            ('sale_order_id', '=', order_id),
        ], limit=1)

    def _kc_compute_compatible_stock_qty(self, ov_line=None):
        self.ensure_one()
        ov_line = ov_line or self.sale_order_line_id
        tech_key = self.kc_technical_key or getattr(ov_line, 'technical_key', False)
        if not ov_line or not tech_key:
            return 0.0
        if hasattr(ov_line, '_kc_get_compatible_available_qty'):
            return ov_line._kc_get_compatible_available_qty(
                warehouse=self.entry_id.warehouse_id,
            )
        return 0.0

    def _kc_planned_qty_from_entry(self):
        """Saldo del plan para este RP (pendiente = planificado − ya en PT)."""
        self.ensure_one()
        plan = self.entry_id.plan_line_id if self.entry_id else False
        if not plan:
            return False
        return plan._kc_qty_for_new_rp()

    def _kc_update_production_qty_suggestion(self, ov_line=None):
        """Recalcula stock/producido informativos y cantidad a producir.

        Si el RP viene de un bloque de planificación, la cantidad sugerida es
        el saldo pendiente del plan (permite parciales; no se reduce por stock).
        """
        self.ensure_one()
        ov_line = ov_line or self.sale_order_line_id or self._kc_resolve_ov_sale_line()
        ov_qty = ov_line.product_uom_qty if ov_line else self.kc_ov_qty or self.qty
        stock_qty = self._kc_compute_compatible_stock_qty(ov_line)
        produced_qty = 0.0
        if ov_line:
            produced_qty = self.env['kc.production.entry']._kc_sum_produced_qty_for_sol(
                ov_line, exclude_entry=self.entry_id)
        planned_qty = self._kc_planned_qty_from_entry()
        if planned_qty is not False:
            qty_to_produce = planned_qty
        else:
            qty_to_produce = max(0.0, ov_qty - stock_qty - produced_qty)
        self.kc_ov_qty = ov_qty
        self.kc_stock_qty = stock_qty
        self.kc_produced_qty = produced_qty
        rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        if self.entry_id.state == 'draft':
            # Plan + parcial: no pisar cantidad ya capturada si está dentro del saldo.
            if (
                self.entry_id.plan_line_id
                and not float_is_zero(self.qty, precision_rounding=rounding)
                and float_compare(self.qty, qty_to_produce, precision_rounding=rounding) <= 0
            ):
                self.kc_qty_to_produce = self.qty
            else:
                self.kc_qty_to_produce = qty_to_produce
                self.qty = qty_to_produce
        else:
            self.kc_qty_to_produce = qty_to_produce

    @api.depends(
        'kc_ov_qty', 'kc_stock_qty', 'kc_produced_qty',
        'sale_order_line_id', 'entry_id', 'entry_id.plan_line_id',
        'entry_id.plan_line_id.planned_qty',
        'entry_id.plan_line_id.qty_produced',
    )
    def _compute_kc_ov_qty_remaining(self):
        Entry = self.env['kc.production.entry']
        for line in self:
            planned_qty = line._kc_planned_qty_from_entry()
            if planned_qty is not False:
                # Tope del RP planificado = saldo pendiente del plan.
                line.kc_ov_qty_remaining = planned_qty
                continue
            if line.sale_order_line_id:
                produced = Entry._kc_sum_produced_qty_for_sol(
                    line.sale_order_line_id, exclude_entry=line.entry_id)
                stock = line.kc_stock_qty
                if not stock and hasattr(line.sale_order_line_id, '_kc_get_compatible_available_qty'):
                    stock = line._kc_compute_compatible_stock_qty(line.sale_order_line_id)
                line.kc_ov_qty_remaining = max(
                    0.0,
                    (line.kc_ov_qty or line.sale_order_line_id.product_uom_qty)
                    - stock - produced,
                )
            else:
                line.kc_ov_qty_remaining = max(
                    0.0, (line.kc_ov_qty or 0.0) - (line.kc_stock_qty or 0.0)
                    - (line.kc_produced_qty or 0.0),
                )

    @api.onchange('sale_order_line_id', 'product_id', 'kc_technical_key', 'entry_id.warehouse_id')
    def _onchange_kc_production_qty_plan(self):
        for line in self:
            line._kc_update_production_qty_suggestion()

    @api.onchange('kc_qty_to_produce')
    def _onchange_kc_qty_to_produce(self):
        rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for line in self:
            line.qty = max(0.0, line.kc_qty_to_produce)
            if float_compare(line.qty, 0.0, precision_rounding=rounding) < 0:
                line.qty = 0.0

    @api.model
    def _kc_find_sale_order_line(self, sale_order, product, qty=0.0,
                                 technical_key=False, kc_unit_cost=0.0,
                                 lot=False, exclude_sol_ids=None):
        """Empareja la línea de OV por producto y especificación (no solo producto)."""
        SaleLine = self.env['sale.order.line']
        if not sale_order or not product:
            return SaleLine
        candidates = sale_order.order_line.filtered(
            lambda l: not l.display_type and l.product_id == product
        )
        if exclude_sol_ids:
            candidates = candidates.filtered(lambda l: l.id not in exclude_sol_ids)
        if not candidates:
            return SaleLine
        if technical_key:
            by_key = candidates.filtered(
                lambda l: getattr(l, 'technical_key', False) == technical_key
            )
            if len(by_key) == 1:
                return by_key
            if by_key:
                candidates = by_key
        if qty:
            by_qty = candidates.filtered(lambda l: l.product_uom_qty == qty)
            if len(by_qty) == 1:
                return by_qty
            if by_qty:
                candidates = by_qty
        if kc_unit_cost and len(candidates) > 1:
            Lot = self.env['stock.lot']
            for sol in candidates:
                tech_key = getattr(sol, 'technical_key', False)
                # Costo de matriz/configuración (no el standard_price del lote
                # valorado, que puede diferir del costo asignado en producción).
                if hasattr(Lot, '_kc_get_standard_price_from_config'):
                    cost = Lot._kc_get_standard_price_from_config(
                        sol.product_id, tech_key)
                else:
                    ov_lot = self._kc_get_lot_from_sale_line(sol)
                    cost = Lot._kc_resolve_unit_cost(
                        sol.product_id,
                        technical_key=tech_key,
                        lot=ov_lot,
                        company=sale_order.company_id,
                    )
                if cost and abs(cost - kc_unit_cost) < 0.0001:
                    return sol
        if lot:
            for sol in candidates:
                if self._kc_get_lot_from_sale_line(sol) == lot:
                    return sol
        if len(candidates) == 1:
            return candidates[:1]
        return SaleLine

    def _kc_ensure_sale_line_link(self, exclude_sol_ids=None):
        """Persiste en BD el vínculo con la línea de OV, lote y especificaciones."""
        self.ensure_one()
        entry = self.entry_id
        if not entry.sale_order_id or not self.product_id:
            return

        sol = self.sale_order_line_id
        if sol and sol.order_id != entry.sale_order_id:
            sol = self.env['sale.order.line']
        if sol and exclude_sol_ids and sol.id in exclude_sol_ids:
            sol = self.env['sale.order.line']

        needs_resync = not sol or not self.lot_id or not self.kc_technical_description
        if needs_resync:
            sol = self._kc_find_sale_order_line(
                entry.sale_order_id,
                self.product_id,
                qty=self.qty,
                technical_key=self.kc_technical_key,
                kc_unit_cost=self.kc_unit_cost,
                lot=self.lot_id,
                exclude_sol_ids=exclude_sol_ids,
            )
        if not sol:
            return

        if needs_resync:
            lot = self._kc_get_lot_from_sale_line(sol)
            desc = self.env['kc.production.entry']._kc_description_from_sale_line(
                sol, lot=lot)
            tech_key = getattr(sol, 'technical_key', False) or False

            write_vals = {
                'sale_order_line_id': sol.id,
                'kc_technical_key': tech_key,
                'kc_technical_description': desc or False,
            }
            if lot and self._kc_is_rp_lot_for_this_order(lot):
                write_vals['lot_id'] = lot.id
            self.write(write_vals)
        return sol.id

    def _kc_refresh_technical_description(self):
        """Actualiza la descripción técnica desde la OV o el lote final."""
        self.ensure_one()
        Entry = self.env['kc.production.entry']
        desc = False
        if self.sale_order_line_id:
            desc = Entry._kc_description_from_sale_line(
                self.sale_order_line_id, lot=self.lot_id)
        if not desc and self.lot_id:
            desc = getattr(self.lot_id, 'technical_description', False)
        if desc != self.kc_technical_description:
            self.write({'kc_technical_description': desc or False})

    def _kc_get_ov_sale_lines_ordered(self):
        """Líneas de OV en el mismo orden con que se construye el RP."""
        self.ensure_one()
        entry = self.entry_id
        if not entry.sale_order_id or not entry.production_line_id:
            return self.env['sale.order.line']
        return entry._kc_filter_sale_lines_for_production(
            entry.sale_order_id, entry.production_line_id)

    def _kc_resolve_ov_sale_line(self):
        """Resuelve la línea de OV de esta fila (vínculo directo o por posición)."""
        self.ensure_one()
        entry = self.entry_id
        SaleLine = self.env['sale.order.line']
        if not entry.sale_order_id:
            return SaleLine
        if (self.sale_order_line_id
                and self.sale_order_line_id.order_id == entry.sale_order_id):
            return self.sale_order_line_id
        ov_lines = self._kc_get_ov_sale_lines_ordered()
        rp_lines = entry.line_ids
        try:
            idx = list(rp_lines).index(self)
        except ValueError:
            idx = -1
        if 0 <= idx < len(ov_lines):
            return ov_lines[idx]
        used_sol_ids = set()
        for sibling in rp_lines:
            if sibling != self and sibling.sale_order_line_id:
                used_sol_ids.add(sibling.sale_order_line_id.id)
        return self._kc_find_sale_order_line(
            entry.sale_order_id,
            self.product_id,
            qty=self.qty,
            technical_key=self.kc_technical_key,
            exclude_sol_ids=used_sol_ids or None,
        )

    def _kc_stabilize_ov_specs(self):
        """Restaura producto/lote/especificaciones; el cliente las pierde al editar costo."""
        self.ensure_one()
        plan = self.entry_id.plan_line_id if self.entry_id else False
        if plan and plan.product_id:
            if self.product_id != plan.product_id:
                self.product_id = plan.product_id
            if not self.uom_id:
                self.uom_id = plan.product_id.uom_id
        if not self.entry_id.sale_order_id:
            return
        sol = self._kc_resolve_ov_sale_line()
        if sol:
            if not self.product_id:
                self.product_id = sol.product_id
            self._kc_apply_sale_line_specs(sol)

    def _kc_apply_sale_line_specs(self, sale_line):
        """Copia especificaciones desde la línea de OV (no lotes de inventario)."""
        self.ensure_one()
        if not sale_line:
            return
        lot = self._kc_get_rp_lot_from_sale_line(sale_line)
        if lot:
            self.lot_id = lot
        if getattr(sale_line, 'technical_key', False):
            self.kc_technical_key = sale_line.technical_key
        desc = self.env['kc.production.entry']._kc_description_from_sale_line(
            sale_line, lot=lot)
        if desc:
            self.kc_technical_description = desc
        if self.sale_order_line_id != sale_line:
            self.sale_order_line_id = sale_line
        self._kc_update_production_qty_suggestion(sale_line)
        self._kc_refresh_weight_area_from_matrix()

    @api.model
    def _kc_enrich_vals_from_sale_order_line(self, vals):
        """Completa lote y especificaciones desde la línea de OV vinculada."""
        sol = self.env['sale.order.line']
        if vals.get('sale_order_line_id'):
            sol = sol.browse(vals['sale_order_line_id'])
        elif vals.get('entry_id') and vals.get('product_id'):
            entry = self.env['kc.production.entry'].browse(vals['entry_id'])
            product = self.env['product.product'].browse(vals['product_id'])
            if entry.sale_order_id:
                sol = self._kc_find_sale_order_line(
                    entry.sale_order_id,
                    product,
                    qty=vals.get('qty', 0.0),
                    technical_key=vals.get('kc_technical_key'),
                    kc_unit_cost=vals.get('kc_unit_cost', 0.0),
                )
                if sol:
                    vals['sale_order_line_id'] = sol.id
        if not sol:
            return vals
        if not vals.get('kc_technical_key') and getattr(sol, 'technical_key', False):
            vals['kc_technical_key'] = sol.technical_key
        if not vals.get('kc_technical_description'):
            desc = self.env['kc.production.entry']._kc_description_from_sale_line(sol)
            if desc:
                vals['kc_technical_description'] = desc
        if vals.get('entry_id') and not vals.get('kc_ov_qty'):
            ov_qty = sol.product_uom_qty
            entry = self.env['kc.production.entry'].browse(vals['entry_id'])
            stock_qty = 0.0
            if hasattr(sol, '_kc_get_compatible_available_qty'):
                stock_qty = sol._kc_get_compatible_available_qty(
                    warehouse=entry.warehouse_id,
                )
            vals.setdefault('kc_ov_qty', ov_qty)
            vals.setdefault('kc_stock_qty', stock_qty)
            # Si viene de plan, saldo pendiente del plan (parciales).
            # No pisar qty si el usuario/contexto ya envió una cantidad.
            if entry.plan_line_id:
                planned = entry.plan_line_id._kc_qty_for_new_rp()
                vals.setdefault('qty', planned)
                vals.setdefault('kc_qty_to_produce', planned)
            else:
                qty_to_produce = max(0.0, ov_qty - stock_qty)
                vals.setdefault('kc_qty_to_produce', qty_to_produce)
                if 'qty' not in vals:
                    vals['qty'] = qty_to_produce
        if 'kc_unit_weight' not in vals or 'kc_unit_area_sqft' not in vals:
            product = sol.product_id
            tech_key = vals.get('kc_technical_key') or getattr(sol, 'technical_key', False)
            weight, area = self.env['product.technical.configuration']._kc_resolve_weight_area(
                product, tech_key,
            )
            vals.setdefault('kc_unit_weight', weight)
            vals.setdefault('kc_unit_area_sqft', area)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        Lot = self.env['stock.lot']
        Configuration = self.env['product.technical.configuration']
        for vals in vals_list:
            entry = self.env['kc.production.entry'].browse(vals['entry_id']) \
                if vals.get('entry_id') else self.env['kc.production.entry']
            if entry.plan_line_id and entry.line_ids:
                raise UserError(_(
                    'Este RP proviene del plan "%(plan)s". No se pueden '
                    'agregar líneas adicionales; use solo la cantidad de la '
                    'línea existente (producción parcial).',
                    plan=entry.plan_line_id.display_name,
                ))
            # OWL a veces reenvía la línea sin product_id al editar costo.
            if not vals.get('product_id'):
                if vals.get('sale_order_line_id'):
                    sol = self.env['sale.order.line'].browse(vals['sale_order_line_id'])
                    vals['product_id'] = sol.product_id.id
                elif entry and entry.plan_line_id and entry.plan_line_id.product_id:
                    vals['product_id'] = entry.plan_line_id.product_id.id
            vals = self._kc_enrich_vals_from_sale_order_line(vals)
            product = self.env['product.product'].browse(vals['product_id']) \
                if vals.get('product_id') else False
            tech_key = vals.get('kc_technical_key')
            if product and ('kc_unit_weight' not in vals or 'kc_unit_area_sqft' not in vals):
                weight, area = Configuration._kc_resolve_weight_area(product, tech_key)
                vals.setdefault('kc_unit_weight', weight)
                vals.setdefault('kc_unit_area_sqft', area)
            if vals.get('kc_unit_cost') or not vals.get('product_id'):
                continue
            company = entry.company_id if entry else self.env.company
            lot = self.env['stock.lot'].browse(vals['lot_id']) \
                if vals.get('lot_id') else False
            vals['kc_unit_cost'] = Lot._kc_resolve_unit_cost(
                product,
                technical_key=tech_key,
                lot=lot,
                company=company,
            )
        return super().create(vals_list)

    def write(self, vals):
        # No permitir vaciar product_id (artefacto del listado editable OWL).
        if 'product_id' in vals and not vals.get('product_id'):
            vals = dict(vals)
            vals.pop('product_id')
        if 'product_id' in vals:
            for line in self:
                plan = line.entry_id.plan_line_id
                if plan and vals['product_id'] != line.product_id.id:
                    raise UserError(_(
                        'Este RP proviene del plan "%(plan)s". No se puede '
                        'cambiar el producto de la línea.',
                        plan=plan.display_name,
                    ))
        return super().write(vals)

    def unlink(self):
        for line in self:
            plan = line.entry_id.plan_line_id
            if plan and not self.env.context.get('kc_allow_plan_line_unlink'):
                raise UserError(_(
                    'Este RP proviene del plan "%(plan)s". No se pueden '
                    'eliminar líneas del detalle.',
                    plan=plan.display_name,
                ))
        return super().unlink()

    @api.onchange('sale_order_line_id')
    def _onchange_sale_order_line_specs(self):
        """Sincroniza lote y descripción técnica desde la línea de OV."""
        if self.sale_order_line_id:
            self._kc_apply_sale_line_specs(self.sale_order_line_id)

    @api.onchange('product_id', 'qty', 'kc_technical_key')
    def _onchange_product_resolve_ov_lot(self):
        """Al elegir producto en un RP con OV, toma el lote creado en ventas.

        No se dispara al editar kc_unit_cost: cambiar el costo manualmente no
        debe re-emparejar ni borrar lote/especificaciones ya cargadas.
        """
        if not self.entry_id.sale_order_id or not self.product_id or not self.qty:
            return
        if self.lot_id and self.kc_technical_description:
            return
        if self.sale_order_line_id:
            self._kc_apply_sale_line_specs(self.sale_order_line_id)
            return
        used_sol_ids = set()
        for sibling in self.entry_id.line_ids:
            if sibling == self:
                continue
            if sibling.sale_order_line_id:
                used_sol_ids.add(sibling.sale_order_line_id.id)
        sol = self._kc_find_sale_order_line(
            self.entry_id.sale_order_id,
            self.product_id,
            qty=self.qty,
            technical_key=self.kc_technical_key,
            kc_unit_cost=self.kc_unit_cost,
            exclude_sol_ids=used_sol_ids or None,
        )
        if sol:
            self._kc_apply_sale_line_specs(sol)

    @api.onchange('product_id', 'kc_technical_key')
    def _onchange_kc_weight_area_from_matrix(self):
        for line in self:
            weight, area = line._kc_resolve_unit_weight_area()
            line.kc_unit_weight = weight
            line.kc_unit_area_sqft = area

    @api.depends('qty', 'kc_unit_cost')
    def _compute_kc_line_cost(self):
        for line in self:
            line.kc_line_cost = line.qty * (line.kc_unit_cost or 0.0)

    @api.depends(
        'kc_unit_cost',
        'sale_order_line_id',
        'sale_order_line_id.price_subtotal',
        'sale_order_line_id.product_uom_qty',
        'sale_order_line_id.product_uom',
        'uom_id',
        'product_id',
        'entry_id.sale_order_id',
    )
    def _compute_sale_cost_check(self):
        digits = self.env['decimal.precision'].precision_get('Product Price')
        for line in self:
            sale_price = line._kc_get_sale_unit_price()
            line.kc_sale_unit_price = sale_price
            line.kc_cost_exceeds_sale = bool(
                sale_price
                and line.kc_unit_cost
                and float_compare(
                    line.kc_unit_cost, sale_price, precision_digits=digits) > 0
            )

    def _kc_get_price_digits(self):
        return self.env['decimal.precision'].precision_get('Product Price')

    def _kc_get_suggested_unit_cost(self):
        """Sugiere costo desde lote, matriz técnica o producto genérico."""
        self.ensure_one()
        if not self.product_id:
            return 0.0
        return self.env['stock.lot']._kc_resolve_unit_cost(
            self.product_id,
            technical_key=self.kc_technical_key,
            lot=self.lot_id,
            company=self.entry_id.company_id,
        )

    def _kc_get_sale_unit_price(self):
        """Precio neto unitario de la línea de OV en la UdM de esta línea."""
        self.ensure_one()
        ov_line = self._find_sale_order_line()
        if not ov_line or not ov_line.product_uom_qty:
            return 0.0
        net_unit = ov_line.price_subtotal / ov_line.product_uom_qty
        if self.uom_id and ov_line.product_uom and self.uom_id != ov_line.product_uom:
            net_unit = ov_line.product_uom._compute_price(net_unit, self.uom_id)
        return net_unit

    @api.onchange('product_id', 'lot_id', 'kc_technical_key')
    def _onchange_kc_unit_cost_suggestion(self):
        if self.product_id and not self.kc_unit_cost:
            self.kc_unit_cost = self._kc_get_suggested_unit_cost()

    @api.onchange('kc_unit_cost')
    def _onchange_kc_unit_cost_sale_check(self):
        # El listado editable OWL descarta campos readonly al cambiar el costo;
        # hay que reinyectarlos explícitamente en cada onchange de costo.
        self._kc_stabilize_ov_specs()
        sale_price = self._kc_get_sale_unit_price()
        digits = self._kc_get_price_digits()
        if (
            sale_price
            and self.kc_unit_cost
            and float_compare(self.kc_unit_cost, sale_price, precision_digits=digits) > 0
        ):
            return {
                'warning': {
                    'title': _('Costo superior al precio de venta'),
                    'message': _(
                        'El costo unitario (%(cost).2f) supera el precio de venta '
                        'de la Orden de Venta (%(price).2f). No podrá validar el '
                        'registro hasta corregir el costo.',
                        cost=self.kc_unit_cost,
                        price=sale_price,
                    ),
                },
            }

    def _kc_apply_lot_unit_cost(self):
        """Escribe el costo en el lote valorado (no en el producto genérico)."""
        self.ensure_one()
        if not self.lot_id or not self.product_id:
            raise UserError(_(
                'La línea de "%(product)s" no tiene lote asignado.',
                product=self.product_id.display_name,
            ))
        if not self.product_id.lot_valuated:
            raise UserError(_(
                'El producto "%(product)s" no está configurado como valorado por '
                'lote. Active valoración por lote para asignar el costo desde '
                'producción.',
                product=self.product_id.display_name,
            ))
        cost = self.kc_unit_cost or 0.0
        digits = self._kc_get_price_digits()
        if float_compare(cost, 0.0, precision_digits=digits) <= 0:
            raise UserError(_(
                'Debe indicar un costo unitario mayor a cero para "%(product)s".',
                product=self.product_id.display_name,
            ))
        self.lot_id.with_company(self.entry_id.company_id).standard_price = cost

    def _kc_get_unit_cost(self):
        """Costo unitario del PT para comparativos."""
        self.ensure_one()
        return self.kc_unit_cost

    def _kc_product_requires_technical_specs(self):
        """True si el PRODUCTO exige lote con especificaciones técnicas.

        Es una propiedad fija del producto (kc_product_custom_specs_lot):
        tiene atributos técnicos configurados, es almacenable y se rastrea por
        lote. Si ese módulo no está instalado, el campo no existe y la lectura
        defensiva devuelve False -> nunca se exige creación técnica.

        Firma estable: recibe solo self y devuelve un booleano.
        """
        self.ensure_one()
        product = self.product_id
        if not product:
            return False
        tmpl = product.product_tmpl_id
        # Campo aportado por kc_product_custom_specs_lot.
        attr_lines = getattr(tmpl, 'technical_attribute_line_ids', False)
        if not attr_lines:
            return False
        # Control globalizado: solo se consideran técnicos los productos cuyo
        # detalle es "Producto + especificaciones y lote" (kc_invoice_detail_mode).
        if getattr(tmpl, 'kc_invoice_detail_mode', False) != 'technical':
            return False
        return product.tracking == 'lot' and getattr(product, 'is_storable', True)

    def _kc_line_sequence_index(self):
        """Posición 1-based de esta línea dentro del RP, para nombrar el lote."""
        self.ensure_one()
        for index, line in enumerate(self.entry_id.line_ids, start=1):
            if line == self:
                return index
        return 1

    def _find_sale_order_line(self):
        """Resuelve la línea de venta de esta línea de RP."""
        self.ensure_one()
        if self.sale_order_line_id:
            return self.sale_order_line_id
        so = self.entry_id.sale_order_id
        if not so or not self.product_id:
            return self.env['sale.order.line']
        return self._kc_resolve_ov_sale_line()

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get('kc_skip_specs_sync'):
            return res
        sync_fields = {
            'product_id', 'qty', 'lot_id', 'sale_order_line_id',
            'kc_technical_key', 'entry_id',
        }
        if sync_fields.intersection(vals):
            for line in self:
                if line.entry_id.sale_order_id and line.product_id:
                    line.with_context(kc_skip_specs_sync=True)._kc_refresh_technical_description()
        return res

    def _resolve_or_create_lot(self):
        """Resuelve o crea el lote de producción (nunca en lote de inventario).

        Con OV: reutiliza solo lotes generados por RP de la misma orden.
        Sin OV (reabastecimiento): conserva la lógica por configuración técnica.
        """
        self.ensure_one()
        entry = self.entry_id
        ov_line = self.sale_order_line_id
        if not ov_line:
            ov_line = self._find_sale_order_line()
        elif ov_line.order_id != entry.sale_order_id:
            ov_line = self._find_sale_order_line()
        Lot = self.env['stock.lot']

        # ---- Reabastecimiento sin OV ----------------------------------------
        if not entry.sale_order_id:
            tech_key = self.kc_technical_key
            if tech_key and hasattr(Lot, '_create_lot_from_configuration'):
                config = self.env['stock.lot'].browse()
                if 'product.technical.configuration' in self.env:
                    config = self.env['product.technical.configuration'].find_by_product_and_key(
                        self.product_id, tech_key)
                if not config:
                    raise UserError(_(
                        'No se encontró una configuración técnica activa para "%(prod)s" '
                        'con la clave %(key)s. Cree la configuración técnica (matriz) '
                        'del producto antes de generar la producción de abastecimiento.'
                    ) % {'prod': self.product_id.display_name, 'key': tech_key})
                nuevo_lote = Lot._create_lot_from_configuration(
                    config, product=self.product_id, company=entry.company_id)
                nuevo_lote.kc_entry_id = entry.id
                return nuevo_lote
            index = self._kc_line_sequence_index()
            codigo = self.product_id.default_code or str(self.product_id.id)
            lot_name = f"LOT-{entry.name}-{codigo}-{str(index).zfill(3)}"
            lot_vals = {
                'name': lot_name,
                'product_id': self.product_id.id,
                'company_id': entry.company_id.id,
            }
            if self.product_id.lot_valuated and self.kc_unit_cost:
                lot_vals['standard_price'] = self.kc_unit_cost
            nuevo_lote = Lot.create(lot_vals)
            nuevo_lote.kc_entry_id = entry.id
            return nuevo_lote

        # ---- Con OV: solo reutilizar lotes de RP de esta orden ---------------
        existing_lot = self.env['stock.lot']
        if self.lot_id and self._kc_is_rp_lot_for_this_order(self.lot_id):
            existing_lot = self.lot_id
        elif ov_line:
            rp_lot = self._kc_get_rp_lot_from_sale_line(ov_line)
            if rp_lot:
                existing_lot = rp_lot
        if existing_lot:
            existing_lot.kc_entry_id = entry.id
            if not existing_lot.kc_sale_order_id:
                existing_lot.kc_sale_order_id = entry.sale_order_id.id
            return existing_lot

        # ---- Crear lote nuevo para la porción producida ----------------------
        if self._kc_product_requires_technical_specs():
            if not ov_line:
                raise UserError(_(
                    'El producto "%s" requiere especificaciones técnicas para '
                    'generar su lote, pero esta línea de producción no está '
                    'vinculada a ninguna línea de la Orden de Venta. Corrija el '
                    'registro antes de confirmar.'
                ) % self.product_id.display_name)
            if not getattr(ov_line, 'technical_key', False):
                raise UserError(_(
                    'El producto "%s" requiere especificaciones técnicas, pero '
                    'la línea de la Orden de Venta no tiene una clave técnica '
                    'definida. Complete las especificaciones en la Orden de '
                    'Venta antes de confirmar la producción.'
                ) % self.product_id.display_name)
            nuevo_lote = Lot._create_from_sale_line(ov_line)
        else:
            index = self._kc_line_sequence_index()
            codigo = self.product_id.default_code or str(self.product_id.id)
            lot_name = f"LOT-{entry.name}-{codigo}-{str(index).zfill(3)}"
            lot_vals = {
                'name': lot_name,
                'product_id': self.product_id.id,
                'company_id': entry.company_id.id,
            }
            if self.product_id.lot_valuated and self.kc_unit_cost:
                lot_vals['standard_price'] = self.kc_unit_cost
            nuevo_lote = Lot.create(lot_vals)

        nuevo_lote.kc_entry_id = entry.id
        if not nuevo_lote.kc_sale_order_id:
            nuevo_lote.kc_sale_order_id = entry.sale_order_id.id
        return nuevo_lote
