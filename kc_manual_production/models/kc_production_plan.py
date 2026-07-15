# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


class KcProductionPlanLine(models.Model):
    """Bloque de planificación de producción (fila del Gantt por centro)."""
    _name = 'kc.production.plan.line'
    _description = 'Bloque de Planificación de Producción'
    _order = 'date_planned_start, id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referencia',
        default='/',
        copy=False,
        readonly=True,
        index=True,
    )
    work_center_id = fields.Many2one(
        comodel_name='kc.work.center',
        string='Centro de Trabajo',
        required=True,
        tracking=True,
        domain="[('id', 'in', allowed_work_center_ids)]",
    )
    allowed_work_center_ids = fields.Many2many(
        comodel_name='kc.work.center',
        compute='_compute_allowed_work_center_ids',
        string='Centros permitidos',
    )
    production_line_id = fields.Many2one(
        related='work_center_id.production_line_id',
        store=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        related='work_center_id.company_id',
        store=True,
        readonly=True,
    )
    origin_type = fields.Selection(
        selection=[
            ('sale_order', 'Orden de Venta'),
            ('replenishment', 'Abastecimiento'),
        ],
        string='Origen',
        required=True,
        default='sale_order',
        tracking=True,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Producto',
        required=True,
        domain="[('tracking', '=', 'lot')]",
    )
    technical_configuration_id = fields.Many2one(
        comodel_name='product.technical.configuration',
        string='Configuración técnica',
        ondelete='restrict',
        copy=False,
        help='Ficha/matriz técnica a producir (abastecimiento). '
             'Rellena clave y descripción automáticamente.',
        domain="[('product_tmpl_id', '=', product_tmpl_id), ('active', '=', True)]",
    )
    product_tmpl_id = fields.Many2one(
        related='product_id.product_tmpl_id',
        string='Plantilla',
        readonly=True,
    )
    technical_key = fields.Char(
        string='Clave técnica',
        help='Ficha / combinación técnica a producir. Obligatoria en PT técnicos; '
             'vacía en producción simple.',
        copy=False,
    )
    technical_description = fields.Text(
        string='Descripción técnica',
        help='Misma descripción técnica de la línea de OV (o de la matriz en abastecimiento).',
        copy=False,
    )
    # Visor directo desde la OV (siempre refleja lo de la línea, como en Ventas).
    sol_technical_description = fields.Text(
        string='Descripción técnica (OV)',
        related='sale_order_line_id.technical_description',
        readonly=True,
    )
    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Orden de Venta',
        domain="[('state', 'in', ['sale', 'done'])]",
    )
    partner_id = fields.Many2one(
        related='sale_order_id.partner_id',
        string='Cliente',
        store=True,
        readonly=True,
    )
    commitment_date = fields.Datetime(
        related='sale_order_id.commitment_date',
        string='Fecha de entrega',
        store=True,
        readonly=True,
        help='Fecha de entrega indicada al cliente en la Orden de Venta.',
    )
    sale_order_line_id = fields.Many2one(
        comodel_name='sale.order.line',
        string='Línea de OV',
        domain="[('order_id', '=', sale_order_id), ('display_type', '=', False)]",
    )
    planned_qty = fields.Float(
        string='Cantidad planificada',
        required=True,
        digits='Product Unit of Measure',
    )
    date_planned_start = fields.Datetime(
        string='Inicio planificado',
        required=True,
        tracking=True,
        default=fields.Datetime.now,
    )
    date_planned_end = fields.Datetime(
        string='Fin planificado',
        required=True,
        tracking=True,
        default=lambda self: fields.Datetime.now() + timedelta(days=1),
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('confirmed', 'Confirmado'),
            ('in_progress', 'En progreso'),
            ('done', 'Hecho'),
            ('cancelled', 'Cancelado'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    priority = fields.Selection(
        selection=[
            ('0', 'Baja'),
            ('1', 'Normal'),
            ('2', 'Alta'),
            ('3', 'Urgente'),
        ],
        string='Prioridad',
        default='1',
        required=True,
    )
    sequence = fields.Integer(default=10)
    entry_id = fields.Many2one(
        comodel_name='kc.production.entry',
        string='Último RP',
        readonly=True,
        copy=False,
        help='Último Registro de Producción generado desde este bloque.',
    )
    entry_ids = fields.One2many(
        comodel_name='kc.production.entry',
        inverse_name='plan_line_id',
        string='Registros de Producción',
        readonly=True,
    )
    qty_produced = fields.Float(
        string='Cantidad producida',
        compute='_compute_qty_produced_variance',
        store=True,
        digits='Product Unit of Measure',
        help='Suma de cantidades validadas (entradas a PT) de todos los RP del plan.',
    )
    qty_remaining = fields.Float(
        string='Pendiente de producir',
        compute='_compute_qty_remaining',
        store=True,
        digits='Product Unit of Measure',
        help='Cantidad planificada menos lo ya validado en PT.',
    )
    variance = fields.Float(
        string='Variación',
        compute='_compute_qty_produced_variance',
        store=True,
        digits='Product Unit of Measure',
        help='Cantidad producida validada menos cantidad planificada.',
    )
    is_delayed = fields.Boolean(
        string='Retrasado',
        compute='_compute_is_delayed',
        search='_search_is_delayed',
        help='Fin planificado ya pasó y el bloque aún no está hecho/cancelado.',
    )
    is_overloaded = fields.Boolean(
        string='Sobrecarga',
        compute='_compute_is_overloaded',
        search='_search_is_overloaded',
        help='Decoración: horas planificadas del centro superan la capacidad '
             'estimada en el rango. No impide guardar.',
    )
    notes = fields.Text(string='Notas')
    color = fields.Integer(compute='_compute_color')

    # ------------------------------------------------------------------
    # Helpers de saldo / origen / ficha técnica
    # ------------------------------------------------------------------

    @api.model
    def _kc_product_requires_technical_specs(self, product):
        """True si el producto es PT técnico (no general / product_only)."""
        if not product:
            return False
        tmpl = product.product_tmpl_id
        if getattr(tmpl, 'kc_simple_production', False):
            return False
        attr_lines = getattr(tmpl, 'technical_attribute_line_ids', False)
        if not attr_lines:
            return False
        if getattr(tmpl, 'kc_invoice_detail_mode', False) != 'technical':
            return False
        return product.tracking == 'lot' and getattr(product, 'is_storable', True)

    @api.model
    def _kc_product_is_simple_production(self, product):
        """True si el PT se produce sin ficha/clave técnica (check en producto)."""
        if not product:
            return False
        tmpl = product.product_tmpl_id
        if not getattr(tmpl, 'kc_simple_production', False):
            return False
        return product.tracking == 'lot' and getattr(product, 'is_storable', True)

    @api.model
    def _kc_sol_is_plannable(self, sol):
        """Línea OV planificable: técnico con clave, o producción simple."""
        if not sol or not sol.product_id:
            return False
        if self._kc_product_is_simple_production(sol.product_id):
            return True
        if not self._kc_product_requires_technical_specs(sol.product_id):
            return False
        key = (getattr(sol, 'technical_key', None) or '').strip()
        return bool(key)

    @api.depends(
        'name', 'origin_type', 'sale_order_id', 'sale_order_id.name',
        'partner_id', 'partner_id.name', 'partner_id.commercial_company_name',
        'product_id', 'product_id.default_code', 'product_id.name',
        'technical_description', 'planned_qty',
    )
    def _compute_display_name(self):
        """Etiqueta Gantt: OV · Cliente · Producto · Specs (crítico para producción)."""
        for rec in self:
            prod = ''
            if rec.product_id:
                prod = (rec.product_id.default_code or '').strip()
                if not prod:
                    prod = (rec.product_id.name or '')[:16]
                elif len(prod) > 16:
                    prod = prod[:14].rstrip() + '…'

            tech = (rec.technical_description or '').strip()
            if tech:
                tech = ' '.join(tech.split())
                if len(tech) > 28:
                    tech = tech[:26].rstrip() + '…'

            if rec.sale_order_id:
                ov = rec.sale_order_id.name or ''
                partner = rec.partner_id
                client = ''
                if partner:
                    client = (
                        partner.commercial_company_name
                        or partner.name
                        or ''
                    )
                    if '(' in client and client.endswith(')'):
                        inner = client[client.rfind('(') + 1:-1].strip()
                        if inner and len(inner) <= 16:
                            client = inner
                    if len(client) > 16:
                        client = client[:14].rstrip() + '…'
                parts = [p for p in (ov, client, prod, tech) if p]
                rec.display_name = ' · '.join(parts) if parts else (rec.name or '')
            elif rec.origin_type == 'replenishment':
                qty = rec.planned_qty or 0.0
                parts = ['Abast.', prod, tech, str(qty) if qty else '']
                parts = [p for p in parts if p]
                rec.display_name = ' · '.join(parts) if parts else (rec.name or 'Abast.')
            else:
                rec.display_name = rec.name or ''

    @api.model
    def _kc_pending_qty_for_sol(self, sol):
        """Cantidad máxima a planificar/producir: OV − ya producido (sin restar stock).

        El stock compatible es informativo en RP; no debe impedir planificar
        lo que se va a fabricar.
        """
        if not sol:
            return 0.0
        Entry = self.env['kc.production.entry']
        produced = Entry._kc_sum_produced_qty_for_sol(sol)
        return max(0.0, (sol.product_uom_qty or 0.0) - produced)

    @api.depends('product_id', 'sale_order_line_id', 'company_id', 'origin_type')
    def _compute_allowed_work_center_ids(self):
        """Solo centros activos de la línea de producción del producto."""
        Entry = self.env['kc.production.entry']
        Center = self.env['kc.work.center']
        for rec in self:
            product = rec.product_id or (
                rec.sale_order_line_id.product_id if rec.sale_order_line_id else False
            )
            line = False
            if product:
                line = Entry._kc_resolve_production_line_for_products(
                    product, company=rec.company_id or self.env.company)
            if line:
                rec.allowed_work_center_ids = Center.search([
                    ('production_line_id', '=', line.id),
                    ('state', '=', 'active'),
                    ('active', '=', True),
                ])
            else:
                rec.allowed_work_center_ids = Center.browse()

    def _kc_apply_sale_order_line(self, sol):
        """Sincroniza producto, ficha técnica y qty desde la línea de OV."""
        self.ensure_one()
        if not sol:
            return
        self.product_id = sol.product_id
        self.technical_key = (getattr(sol, 'technical_key', None) or '').strip() or False
        desc = getattr(sol, 'technical_description', False) or False
        if not desc:
            desc = self.env['kc.production.entry']._kc_description_from_sale_line(sol)
        self.technical_description = desc
        if not self.sale_order_id:
            self.sale_order_id = sol.order_id
        if float_compare(self.planned_qty or 0.0, 0.0, precision_digits=4) <= 0:
            self.planned_qty = self._kc_pending_qty_for_sol(sol)

    def _kc_suggest_work_center(self, product):
        """Primer centro activo de la línea de producción del producto."""
        self.ensure_one()
        if not product:
            return self.env['kc.work.center']
        line = self.env['kc.production.entry']._kc_resolve_production_line_for_products(
            product, company=self.company_id or self.env.company)
        if not line:
            return self.env['kc.work.center']
        return self.env['kc.work.center'].search([
            ('production_line_id', '=', line.id),
            ('state', '=', 'active'),
            ('active', '=', True),
        ], order='sequence, id', limit=1)

    def _kc_apply_technical_configuration(self, config, suggest_qty=True):
        """Copia clave/descripción desde la ficha; qty opcional desde regla técnica."""
        self.ensure_one()
        if not config:
            self.technical_key = False
            self.technical_description = False
            return
        self.technical_key = (config.technical_key or '').strip() or False
        self.technical_description = config.technical_description or False
        if not suggest_qty:
            return
        if float_compare(self.planned_qty or 0.0, 0.0, precision_digits=4) > 0:
            return
        if 'kc.technical.orderpoint' not in self.env:
            return
        rule = self.env['kc.technical.orderpoint'].search([
            ('product_id', '=', self.product_id.id),
            ('technical_configuration_id', '=', config.id),
            ('company_id', '=', (self.company_id or self.env.company).id),
            ('active', '=', True),
        ], limit=1)
        if rule and float_compare(
                rule.qty_to_order_spec or 0.0, 0.0, precision_digits=4) > 0:
            self.planned_qty = rule.qty_to_order_spec

    @api.onchange('origin_type')
    def _onchange_origin_type(self):
        if self.origin_type == 'replenishment':
            self.sale_order_id = False
            self.sale_order_line_id = False
        elif self.origin_type == 'sale_order':
            self.technical_configuration_id = False
            if not self.sale_order_line_id:
                self.product_id = False
                self.technical_key = False
                self.technical_description = False

    @api.onchange('sale_order_id')
    def _onchange_sale_order_id(self):
        if self.sale_order_id and self.sale_order_line_id:
            if self.sale_order_line_id.order_id != self.sale_order_id:
                self.sale_order_line_id = False
                self.product_id = False
                self.technical_key = False
                self.technical_description = False

    @api.onchange('sale_order_line_id')
    def _onchange_sale_order_line_id(self):
        if self.origin_type != 'sale_order':
            return
        if not self.sale_order_line_id:
            self.technical_key = False
            self.technical_description = False
            return
        if not self._kc_sol_is_plannable(self.sale_order_line_id):
            sol = self.sale_order_line_id
            self.sale_order_line_id = False
            self.product_id = False
            self.technical_key = False
            self.technical_description = False
            return {
                'warning': {
                    'title': _('Línea no planificable'),
                    'message': _(
                        'La línea "%(line)s" no es planificable. Use un producto '
                        'técnico con clave en la OV, o un producto con '
                        '"Producción simple" activado.',
                        line=sol.display_name,
                    ),
                },
            }
        self._kc_apply_sale_order_line(self.sale_order_line_id)
        center = self._kc_suggest_work_center(self.sale_order_line_id.product_id)
        if center and (
            not self.work_center_id
            or self.work_center_id.production_line_id != center.production_line_id
        ):
            self.work_center_id = center

    @api.onchange('product_id')
    def _onchange_product_id_technical(self):
        if self.origin_type != 'replenishment' or not self.product_id:
            return
        if not self._kc_product_requires_technical_specs(self.product_id):
            product = self.product_id
            self.product_id = False
            self.technical_configuration_id = False
            self.technical_key = False
            self.technical_description = False
            title = _('Producto no apto para abastecimiento')
            if self._kc_product_is_simple_production(product):
                message = _(
                    'El producto "%(product)s" es de producción simple: se '
                    'planifica desde la OV, no por abastecimiento.',
                    product=product.display_name,
                )
            else:
                message = _(
                    'El producto "%(product)s" es general (sin modo ficha '
                    'técnica). Elija un PT con atributos técnicos.',
                    product=product.display_name,
                )
            return {
                'warning': {
                    'title': title,
                    'message': message,
                },
            }
        # Si la config no pertenece al nuevo producto, limpiar.
        cfg = self.technical_configuration_id
        if cfg and cfg.product_tmpl_id != self.product_id.product_tmpl_id:
            self.technical_configuration_id = False
            self.technical_key = False
            self.technical_description = False
        center = self._kc_suggest_work_center(self.product_id)
        if center and (
            not self.work_center_id
            or self.work_center_id.production_line_id != center.production_line_id
        ):
            self.work_center_id = center

    @api.onchange('technical_configuration_id')
    def _onchange_technical_configuration_id(self):
        if self.origin_type != 'replenishment':
            return
        if not self.technical_configuration_id:
            self.technical_key = False
            self.technical_description = False
            return
        cfg = self.technical_configuration_id
        if self.product_id and cfg.product_tmpl_id != self.product_id.product_tmpl_id:
            self.technical_configuration_id = False
            self.technical_key = False
            self.technical_description = False
            return {
                'warning': {
                    'title': _('Configuración inválida'),
                    'message': _(
                        'La configuración técnica no pertenece al producto seleccionado.'
                    ),
                },
            }
        self._kc_apply_technical_configuration(cfg, suggest_qty=True)

    def _kc_sum_validated_produced_qty(self):
        """Suma qty validada en PT de todos los RP no revertidos de este plan."""
        self.ensure_one()
        qty = 0.0
        entries = self.entry_ids.filtered(
            lambda e: e.state == 'done' and not e.is_reversal and not e.reversed_by_id
        )
        for entry in entries:
            lines = entry.line_ids.filtered(lambda l: l.product_id == self.product_id)
            if self.sale_order_line_id:
                lines = lines.filtered(
                    lambda l: l.sale_order_line_id == self.sale_order_line_id
                )
            qty += sum(lines.mapped('qty'))
        return qty

    def _kc_qty_for_new_rp(self):
        """Cantidad sugerida al generar un RP (saldo pendiente del plan)."""
        self.ensure_one()
        return max(0.0, (self.planned_qty or 0.0) - self._kc_sum_validated_produced_qty())

    @api.depends(
        'entry_ids', 'entry_ids.state', 'entry_ids.line_ids.qty',
        'entry_ids.line_ids.product_id', 'entry_ids.line_ids.sale_order_line_id',
        'entry_ids.reversal_of_id', 'product_id', 'sale_order_line_id', 'planned_qty',
    )
    def _compute_qty_produced_variance(self):
        for rec in self:
            qty = rec._kc_sum_validated_produced_qty()
            rec.qty_produced = qty
            rec.variance = qty - (rec.planned_qty or 0.0)

    @api.depends('planned_qty', 'qty_produced')
    def _compute_qty_remaining(self):
        for rec in self:
            rec.qty_remaining = max(
                0.0, (rec.planned_qty or 0.0) - (rec.qty_produced or 0.0),
            )

    @api.depends('date_planned_end', 'state')
    def _compute_is_delayed(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.is_delayed = bool(
                rec.date_planned_end
                and rec.date_planned_end < now
                and rec.state in ('draft', 'confirmed', 'in_progress')
            )

    @api.model
    def _search_is_delayed(self, operator, value):
        """Permite filtrar retrasados sin almacenar is_delayed (D4)."""
        if operator not in ('=', '!='):
            raise UserError(_('Operador no soportado en filtro de retraso.'))
        want_delayed = (operator == '=' and bool(value)) or (
            operator == '!=' and not bool(value)
        )
        now = fields.Datetime.now()
        delayed_domain = [
            ('date_planned_end', '<', now),
            ('state', 'in', ('draft', 'confirmed', 'in_progress')),
        ]
        if want_delayed:
            return delayed_domain
        return ['!'] + delayed_domain

    @api.depends('work_center_id', 'date_planned_start', 'date_planned_end', 'state')
    def _compute_is_overloaded(self):
        Plan = self.env['kc.production.plan.line']
        for rec in self:
            rec.is_overloaded = False
            if not rec.work_center_id or not rec.date_planned_start or not rec.date_planned_end:
                continue
            if rec.state == 'cancelled':
                continue
            duration_h = max(
                (rec.date_planned_end - rec.date_planned_start).total_seconds() / 3600.0,
                0.0,
            )
            siblings = Plan.search([
                ('id', '!=', rec.id or 0),
                ('work_center_id', '=', rec.work_center_id.id),
                ('state', '!=', 'cancelled'),
                ('date_planned_start', '<', rec.date_planned_end),
                ('date_planned_end', '>', rec.date_planned_start),
            ])
            sibling_h = 0.0
            for sib in siblings:
                start = max(sib.date_planned_start, rec.date_planned_start)
                end = min(sib.date_planned_end, rec.date_planned_end)
                if end > start:
                    sibling_h += (end - start).total_seconds() / 3600.0
            available = rec._kc_estimate_available_hours()
            if available > 0 and (duration_h + sibling_h) > available:
                rec.is_overloaded = True

    @api.model
    def _search_is_overloaded(self, operator, value):
        """Permite filtrar sobrecarga sin almacenar is_overloaded."""
        if operator not in ('=', '!='):
            raise UserError(_('Operador no soportado en filtro de sobrecarga.'))
        want_overloaded = (operator == '=' and bool(value)) or (
            operator == '!=' and not bool(value)
        )
        candidates = self.search([('state', '!=', 'cancelled')])
        overloaded_ids = candidates.filtered(lambda r: r.is_overloaded).ids
        if want_overloaded:
            return [('id', 'in', overloaded_ids)]
        return [('id', 'not in', overloaded_ids)]

    def _kc_estimate_available_hours(self):
        """Horas disponibles del centro en el rango del bloque (estimación)."""
        self.ensure_one()
        center = self.work_center_id
        if not self.date_planned_start or not self.date_planned_end:
            return 0.0
        span_h = max(
            (self.date_planned_end - self.date_planned_start).total_seconds() / 3600.0,
            0.0,
        )
        capacity = center.capacity_qty or 1.0
        efficiency = (center.efficiency_pct or 100.0) / 100.0
        if center.capacity_time_uom == 'day':
            days = max(span_h / 24.0, 1.0 / 24.0)
            return days * capacity * 8.0 * efficiency
        if center.capacity_time_uom == 'shift':
            shifts = max(span_h / 8.0, 0.125)
            return shifts * capacity * 8.0 * efficiency
        # hour
        return span_h * capacity * efficiency

    @api.depends('state', 'is_delayed', 'is_overloaded')
    def _compute_color(self):
        mapping = {
            'draft': 0,
            'confirmed': 4,
            'in_progress': 3,
            'done': 10,
            'cancelled': 1,
        }
        for rec in self:
            if rec.is_delayed and rec.state not in ('done', 'cancelled'):
                rec.color = 1
            elif rec.is_overloaded and rec.state not in ('done', 'cancelled'):
                rec.color = 2
            else:
                rec.color = mapping.get(rec.state, 0)

    @api.constrains('date_planned_start', 'date_planned_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_planned_start and rec.date_planned_end:
                if rec.date_planned_end <= rec.date_planned_start:
                    raise ValidationError(_(
                        'El fin planificado debe ser posterior al inicio '
                        '(%s).'
                    ) % rec.display_name)

    @api.constrains('work_center_id', 'date_planned_start', 'date_planned_end', 'state')
    def _check_no_overlap(self):
        if self.env.context.get('kc_allow_plan_overlap'):
            return
        for rec in self:
            if rec.state == 'cancelled' or not rec.work_center_id:
                continue
            if not rec.date_planned_start or not rec.date_planned_end:
                continue
            overlapping = self.search([
                ('id', '!=', rec.id),
                ('work_center_id', '=', rec.work_center_id.id),
                ('state', '!=', 'cancelled'),
                ('date_planned_start', '<', rec.date_planned_end),
                ('date_planned_end', '>', rec.date_planned_start),
            ], limit=1)
            if overlapping:
                raise ValidationError(_(
                    'El centro "%(center)s" ya tiene el bloque %(other)s '
                    'en el mismo intervalo.',
                    center=rec.work_center_id.display_name,
                    other=overlapping.display_name,
                ))

    @api.constrains('work_center_id', 'state')
    def _check_work_center_active(self):
        for rec in self:
            if rec.state == 'cancelled':
                continue
            if rec.work_center_id and rec.work_center_id.state != 'active':
                raise ValidationError(_(
                    'El centro de trabajo "%s" no está activo. No se puede '
                    'crear ni confirmar el bloque de planificación.'
                ) % rec.work_center_id.display_name)

    @api.constrains(
        'origin_type', 'sale_order_id', 'sale_order_line_id',
        'product_id', 'planned_qty', 'work_center_id',
        'technical_key',
    )
    def _check_origin_and_qty(self):
        for rec in self:
            if rec.state == 'cancelled':
                continue
            is_simple = rec._kc_product_is_simple_production(rec.product_id)
            key = (rec.technical_key or '').strip()

            if is_simple:
                if rec.origin_type == 'replenishment':
                    raise ValidationError(_(
                        'El producto "%(product)s" está marcado como producción '
                        'simple: no usa abastecimiento. Planifique desde la OV.',
                        product=rec.product_id.display_name,
                    ))
                if rec.origin_type != 'sale_order':
                    raise ValidationError(_(
                        'La producción simple solo se planifica desde Orden de Venta.'
                    ))
                if not rec.sale_order_id or not rec.sale_order_line_id:
                    raise ValidationError(_(
                        'El bloque %(name)s de origen OV requiere Orden de Venta '
                        'y Línea de OV.',
                        name=rec.display_name,
                    ))
                if not rec._kc_sol_is_plannable(rec.sale_order_line_id):
                    raise ValidationError(_(
                        'La línea de OV no es planificable (producción simple).'
                    ))
                if rec.sale_order_line_id.order_id != rec.sale_order_id:
                    raise ValidationError(_(
                        'La línea de OV no pertenece a la orden seleccionada.'
                    ))
                if rec.product_id != rec.sale_order_line_id.product_id:
                    raise ValidationError(_(
                        'El producto del plan debe ser el de la línea de OV '
                        '(%s).'
                    ) % rec.sale_order_line_id.product_id.display_name)
                pending = rec._kc_pending_qty_for_sol(rec.sale_order_line_id)
                ov_qty = rec.sale_order_line_id.product_uom_qty or 0.0
                if float_compare(rec.planned_qty, 0.0, precision_digits=4) <= 0:
                    raise ValidationError(_(
                        'La cantidad planificada debe ser mayor que cero.'
                    ))
                if float_compare(rec.planned_qty, ov_qty, precision_digits=4) > 0:
                    raise ValidationError(_(
                        'La cantidad planificada (%(qty)s) no puede superar '
                        'la cantidad de la OV (%(ov)s).',
                        qty=rec.planned_qty,
                        ov=ov_qty,
                    ))
                if float_compare(rec.planned_qty, pending, precision_digits=4) > 0:
                    raise ValidationError(_(
                        'La cantidad planificada (%(qty)s) supera lo pendiente '
                        'de producir (%(pending)s = OV − ya fabricado).',
                        qty=rec.planned_qty,
                        pending=pending,
                    ))
                expected = self.env['kc.production.entry']._kc_resolve_production_line_for_products(
                    rec.sale_order_line_id.product_id,
                    company=rec.company_id,
                )
                if expected and rec.production_line_id and expected != rec.production_line_id:
                    raise ValidationError(_(
                        'El centro "%(center)s" pertenece a la línea '
                        '"%(got)s", pero el producto de la OV corresponde a '
                        '"%(expected)s".',
                        center=rec.work_center_id.display_name,
                        got=rec.production_line_id.display_name,
                        expected=expected.display_name,
                    ))
                continue

            if not key:
                raise ValidationError(_(
                    'El bloque %(name)s requiere clave técnica (ficha). '
                    'No se permite planificar PT generales sin atributos '
                    'técnicos. Active "Producción simple" en el producto '
                    'si no usa ficha técnica.',
                    name=rec.display_name,
                ))
            if not rec._kc_product_requires_technical_specs(rec.product_id):
                raise ValidationError(_(
                    'El producto "%(product)s" no es técnico (modo ficha). '
                    'Solo se planifican productos con atributos técnicos, '
                    'o con "Producción simple" activado.',
                    product=rec.product_id.display_name,
                ))
            if rec.origin_type == 'sale_order':
                if not rec.sale_order_id or not rec.sale_order_line_id:
                    raise ValidationError(_(
                        'El bloque %(name)s de origen OV requiere Orden de Venta '
                        'y Línea de OV.',
                        name=rec.display_name,
                    ))
                if not rec._kc_sol_is_plannable(rec.sale_order_line_id):
                    raise ValidationError(_(
                        'La línea de OV no tiene ficha técnica completa '
                        '(producto técnico + clave técnica).'
                    ))
                sol_key = (rec.sale_order_line_id.technical_key or '').strip()
                if sol_key != key:
                    raise ValidationError(_(
                        'La clave técnica del plan debe coincidir con la de la OV.'
                    ))
                if rec.sale_order_line_id.order_id != rec.sale_order_id:
                    raise ValidationError(_(
                        'La línea de OV no pertenece a la orden seleccionada.'
                    ))
                if rec.product_id != rec.sale_order_line_id.product_id:
                    raise ValidationError(_(
                        'El producto del plan debe ser el de la línea de OV '
                        '(%s).'
                    ) % rec.sale_order_line_id.product_id.display_name)
                pending = rec._kc_pending_qty_for_sol(rec.sale_order_line_id)
                ov_qty = rec.sale_order_line_id.product_uom_qty or 0.0
                if float_compare(rec.planned_qty, 0.0, precision_digits=4) <= 0:
                    raise ValidationError(_(
                        'La cantidad planificada debe ser mayor que cero.'
                    ))
                if float_compare(rec.planned_qty, ov_qty, precision_digits=4) > 0:
                    raise ValidationError(_(
                        'La cantidad planificada (%(qty)s) no puede superar '
                        'la cantidad de la OV (%(ov)s).',
                        qty=rec.planned_qty,
                        ov=ov_qty,
                    ))
                if float_compare(rec.planned_qty, pending, precision_digits=4) > 0:
                    raise ValidationError(_(
                        'La cantidad planificada (%(qty)s) supera lo pendiente '
                        'de producir (%(pending)s = OV − ya fabricado).',
                        qty=rec.planned_qty,
                        pending=pending,
                    ))
                expected = self.env['kc.production.entry']._kc_resolve_production_line_for_products(
                    rec.sale_order_line_id.product_id,
                    company=rec.company_id,
                )
                if expected and rec.production_line_id and expected != rec.production_line_id:
                    raise ValidationError(_(
                        'El centro "%(center)s" pertenece a la línea '
                        '"%(got)s", pero el producto de la OV corresponde a '
                        '"%(expected)s".',
                        center=rec.work_center_id.display_name,
                        got=rec.production_line_id.display_name,
                        expected=expected.display_name,
                    ))
            elif rec.origin_type == 'replenishment':
                if rec.sale_order_id or rec.sale_order_line_id:
                    raise ValidationError(_(
                        'Un bloque de abastecimiento no debe tener Orden de Venta.'
                    ))
                if not rec.product_id:
                    raise ValidationError(_(
                        'El bloque de abastecimiento requiere un producto.'
                    ))
                if float_compare(rec.planned_qty or 0.0, 0.0, precision_digits=4) <= 0:
                    raise ValidationError(_(
                        'La cantidad planificada debe ser mayor que cero.'
                    ))
                # Validar / alinear con matriz técnica.
                if 'product.technical.configuration' in self.env:
                    Config = self.env['product.technical.configuration']
                    conf = rec.technical_configuration_id
                    if conf:
                        if conf.product_tmpl_id != rec.product_id.product_tmpl_id:
                            raise ValidationError(_(
                                'La configuración técnica no pertenece al producto '
                                '"%s".'
                            ) % rec.product_id.display_name)
                        conf_key = (conf.technical_key or '').strip()
                        if conf_key != key:
                            raise ValidationError(_(
                                'La clave técnica del plan debe coincidir con la '
                                'de la configuración seleccionada.'
                            ))
                    else:
                        conf = Config.search([
                            ('product_tmpl_id', '=', rec.product_id.product_tmpl_id.id),
                            ('technical_key', '=', key),
                            ('active', '=', True),
                        ], limit=1)
                        if not conf:
                            raise ValidationError(_(
                                'La clave técnica "%(key)s" no existe en la matriz '
                                'del producto "%(product)s". Seleccione una '
                                'configuración técnica.',
                                key=key,
                                product=rec.product_id.display_name,
                            ))
                if rec.production_line_id and rec.product_id:
                    line = self.env['kc.production.entry']._kc_resolve_production_line_for_products(
                        rec.product_id, company=rec.company_id,
                    )
                    if line and line != rec.production_line_id:
                        raise ValidationError(_(
                            'El producto "%(product)s" no corresponde a la línea '
                            'del centro "%(center)s".',
                            product=rec.product_id.display_name,
                            center=rec.work_center_id.display_name,
                        ))

    @api.model_create_multi
    def create(self, vals_list):
        Config = self.env['product.technical.configuration'] if (
            'product.technical.configuration' in self.env) else False
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'kc.production.plan.line') or '/'
            # Asegurar producto desde SOL si falta (create desde context).
            sol_id = vals.get('sale_order_line_id')
            if sol_id:
                sol = self.env['sale.order.line'].browse(sol_id)
                if not vals.get('product_id'):
                    vals['product_id'] = sol.product_id.id
                vals.setdefault('sale_order_id', sol.order_id.id)
                if not vals.get('technical_key'):
                    vals['technical_key'] = (sol.technical_key or '').strip() or False
                if not vals.get('technical_description'):
                    desc = getattr(sol, 'technical_description', False) or False
                    if not desc:
                        desc = self.env['kc.production.entry']._kc_description_from_sale_line(sol)
                    vals['technical_description'] = desc
                if float_compare(vals.get('planned_qty') or 0.0, 0.0, precision_digits=4) <= 0:
                    vals['planned_qty'] = self._kc_pending_qty_for_sol(sol)
            vals.setdefault(
                'origin_type',
                'sale_order' if vals.get('sale_order_line_id') else 'replenishment',
            )
            # Abastecimiento: sincronizar ficha desde configuración técnica.
            if vals.get('origin_type') == 'replenishment' and Config:
                conf = False
                if vals.get('technical_configuration_id'):
                    conf = Config.browse(vals['technical_configuration_id'])
                elif vals.get('technical_key') and vals.get('product_id'):
                    product = self.env['product.product'].browse(vals['product_id'])
                    conf = Config.search([
                        ('product_tmpl_id', '=', product.product_tmpl_id.id),
                        ('technical_key', '=', (vals.get('technical_key') or '').strip()),
                        ('active', '=', True),
                    ], limit=1)
                    if conf:
                        vals['technical_configuration_id'] = conf.id
                if conf:
                    vals['technical_key'] = (conf.technical_key or '').strip() or False
                    if not vals.get('technical_description'):
                        vals['technical_description'] = conf.technical_description or False
        records = super().create(vals_list)
        records.mapped('sale_order_id').invalidate_recordset(['kc_production_progress_ids'])
        return records

    def write(self, vals):
        if vals.get('technical_configuration_id') and 'product.technical.configuration' in self.env:
            conf = self.env['product.technical.configuration'].browse(
                vals['technical_configuration_id'])
            if conf:
                vals.setdefault('technical_key', (conf.technical_key or '').strip() or False)
                vals.setdefault(
                    'technical_description', conf.technical_description or False)
        res = super().write(vals)
        self.mapped('sale_order_id').invalidate_recordset(['kc_production_progress_ids'])
        return res

    def unlink(self):
        done = self.filtered(lambda r: r.state == 'done')
        if done:
            raise UserError(_(
                'No se pueden eliminar planes en estado Hecho: %(plans)s.',
                plans=', '.join(done.mapped('display_name')),
            ))
        return super().unlink()

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Solo se confirman bloques en borrador.'))
            if rec.work_center_id.state != 'active':
                raise UserError(_(
                    'El centro "%s" no está activo.'
                ) % rec.work_center_id.display_name)
            rec.state = 'confirmed'
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state not in ('draft', 'confirmed'):
                raise UserError(_(
                    'Solo se pueden cancelar bloques en borrador o confirmados. '
                    'Si ya hay un RP validado, use la reversión del RP.'
                ))
            done_rp = rec.entry_ids.filtered(
                lambda e: e.state == 'done' and not e.is_reversal and not e.reversed_by_id
            )[:1]
            if done_rp:
                raise UserError(_(
                    'El bloque %(plan)s tiene el RP %(rp)s validado. '
                    'Cancele mediante la reversión del RP.',
                    plan=rec.display_name,
                    rp=done_rp.display_name,
                ))
            rec.state = 'cancelled'
        return True

    def action_draft(self):
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_('Solo se puede reabrir un bloque cancelado.'))
            rec.state = 'draft'
        return True

    def action_create_entry(self):
        """Abre o crea RP desde el bloque (soporta producción parcial)."""
        self.ensure_one()
        if self.state not in ('draft', 'confirmed', 'in_progress'):
            raise UserError(_(
                'Solo se puede generar RP desde bloques en borrador, '
                'confirmados o en progreso.'
            ))
        if self.work_center_id.state != 'active':
            raise UserError(_(
                'El centro "%s" no está activo.'
            ) % self.work_center_id.display_name)

        Entry = self.env['kc.production.entry']
        open_rp = Entry.search([
            ('plan_line_id', '=', self.id),
            ('state', 'in', ('draft', 'confirmed')),
            ('reversal_of_id', '=', False),
        ], limit=1)
        if open_rp:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Registro de Producción'),
                'res_model': 'kc.production.entry',
                'res_id': open_rp.id,
                'view_mode': 'form',
                'target': 'current',
            }

        qty = self._kc_qty_for_new_rp()
        rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        if float_compare(qty, 0.0, precision_rounding=rounding) <= 0:
            raise UserError(_(
                'El bloque %(plan)s ya tiene cubierta la cantidad planificada '
                '(%(planned)s). No hay saldo para un nuevo RP.',
                plan=self.display_name,
                planned=self.planned_qty,
            ))

        line_vals = {
            'product_id': self.product_id.id,
            'qty': qty,
            'kc_qty_to_produce': qty,
            'uom_id': self.product_id.uom_id.id,
            'kc_technical_key': self.technical_key or False,
            'kc_technical_description': self.technical_description or False,
        }
        if self.sale_order_line_id:
            line_vals['sale_order_line_id'] = self.sale_order_line_id.id
            line_vals['kc_ov_qty'] = self.sale_order_line_id.product_uom_qty
        ctx = {
            'default_production_line_id': self.production_line_id.id,
            'default_work_center_id': self.work_center_id.id,
            'default_plan_line_id': self.id,
            'default_sale_order_id': self.sale_order_id.id or False,
            'default_line_ids': [(0, 0, line_vals)],
            # Evita que el onchange de OV vuelva a cargar todas las líneas.
            'kc_from_plan_line': True,
        }
        if self.origin_type == 'replenishment':
            ctx['default_created_from_replenishment'] = True
            ctx['default_sale_order_id'] = False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registro de Producción'),
            'res_model': 'kc.production.entry',
            'view_mode': 'form',
            'target': 'current',
            'context': ctx,
        }

    def _kc_sync_from_entry(self, entry, event):
        """Única sincronización de estado plan ← RP (confirm / validate).

        Usa kc_allow_plan_overlap solo al cambiar estado (no toca fechas/centro),
        para no romper el control de solape en altas/edición de agenda.
        """
        self.ensure_one()
        if not entry:
            return
        plan = self.with_context(kc_allow_plan_overlap=True)
        rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        if event == 'confirm' and self.state in ('draft', 'confirmed'):
            plan.write({
                'state': 'in_progress',
                'entry_id': entry.id,
            })
        elif event == 'validate':
            produced = self._kc_sum_validated_produced_qty()
            vals = {'entry_id': entry.id}
            if float_compare(
                produced, self.planned_qty or 0.0, precision_rounding=rounding,
            ) >= 0:
                vals['state'] = 'done'
            elif self.state != 'in_progress':
                vals['state'] = 'in_progress'
            plan.write(vals)