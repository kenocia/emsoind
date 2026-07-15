# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class SaleOrder(models.Model):
    """Extensión de la Orden de Venta para trazabilidad de producción manual."""
    _inherit = 'sale.order'

    kc_lot_ids = fields.One2many(
        comodel_name='stock.lot',
        inverse_name='kc_sale_order_id',
        string='Lotes Generados',
    )
    kc_lot_count = fields.Integer(
        string='N° Lotes',
        compute='_compute_kc_lot_count',
    )
    kc_entry_ids = fields.One2many(
        comodel_name='kc.production.entry',
        inverse_name='sale_order_id',
        string='Registros de Producción',
    )
    kc_entry_count = fields.Integer(
        string='N° Registros de Producción',
        compute='_compute_kc_entry_count',
    )
    kc_consumption_ids = fields.One2many(
        comodel_name='kc.production.consumption',
        inverse_name='sale_order_id',
        string='Consumos de MP',
    )
    kc_consumption_count = fields.Integer(
        string='N° Consumos de MP',
        compute='_compute_kc_consumption_count',
    )
    kc_production_status_ids = fields.One2many(
        comodel_name='kc.sale.order.production.status',
        inverse_name='sale_order_id',
        string='Estado de Producción por Línea',
        compute='_compute_kc_production_status_ids',
    )
    kc_production_progress_ids = fields.One2many(
        comodel_name='kc.sale.order.production.progress',
        inverse_name='sale_order_id',
        string='Avance de Producción por Producto',
        compute='_compute_kc_production_progress_ids',
    )
    kc_production_line_required_count = fields.Integer(
        string='Líneas de producción requeridas',
        compute='_compute_kc_production_counters',
    )
    kc_production_line_done_count = fields.Integer(
        string='Líneas de producción validadas',
        compute='_compute_kc_production_counters',
    )
    kc_production_line_pending_count = fields.Integer(
        string='Líneas de producción pendientes',
        compute='_compute_kc_production_counters',
    )
    kc_production_incomplete = fields.Boolean(
        string='Producción incompleta',
        compute='_compute_kc_production_counters',
    )

    @api.depends('kc_lot_ids')
    def _compute_kc_lot_count(self):
        for order in self:
            order.kc_lot_count = len(order.kc_lot_ids)

    @api.depends('kc_entry_ids')
    def _compute_kc_entry_count(self):
        for order in self:
            order.kc_entry_count = len(order.kc_entry_ids)

    @api.depends('kc_consumption_ids')
    def _compute_kc_consumption_count(self):
        for order in self:
            order.kc_consumption_count = len(order.kc_consumption_ids)

    def _kc_get_producible_order_lines(self):
        """Líneas de la OV elegibles para RP (PT con rastreo por lote)."""
        self.ensure_one()
        return self.order_line.filtered(
            lambda l: not l.display_type
            and l.product_id
            and l.product_id.tracking == 'lot'
        )

    def _kc_group_order_lines_by_production_line(self):
        """Agrupa líneas producibles de la OV por línea de producción."""
        self.ensure_one()
        Line = self.env['kc.production.line']
        groups = {}
        unassigned = self.env['sale.order.line']
        for ov_line in self._kc_get_producible_order_lines():
            prod_line = Line.resolve_for_product(
                ov_line.product_id, company=self.company_id)
            if prod_line:
                groups.setdefault(prod_line, self.env['sale.order.line'])
                groups[prod_line] |= ov_line
            else:
                unassigned |= ov_line
        return groups, unassigned

    def _kc_get_open_entry_for_line(self, production_line):
        """RP en curso (draft/confirmed) para esta OV y línea."""
        self.ensure_one()
        open_states = self.env['kc.production.entry']._kc_open_entry_states()
        entries = self.kc_entry_ids.filtered(
            lambda e: e.production_line_id == production_line
            and not e.is_reversal
            and e.state in open_states
            and not e.reversed_by_id
        )
        return entries[:1]

    def _kc_get_active_entry_for_line(self, production_line):
        """Compat: RP en curso; si no hay, el último done (solo informativo)."""
        self.ensure_one()
        open_entry = self._kc_get_open_entry_for_line(production_line)
        if open_entry:
            return open_entry
        done = self.kc_entry_ids.filtered(
            lambda e: e.production_line_id == production_line
            and not e.is_reversal
            and e.state == 'done'
            and not e.reversed_by_id
        )
        return done.sorted('id', reverse=True)[:1]

    def _kc_sol_remaining_qty(self, ov_line, warehouse=None):
        """Saldo pendiente de una línea de OV (ov − stock − producido)."""
        Entry = self.env['kc.production.entry']
        stock = 0.0
        if hasattr(ov_line, '_kc_get_compatible_available_qty'):
            stock = ov_line._kc_get_compatible_available_qty(warehouse=warehouse) or 0.0
        produced = Entry._kc_sum_produced_qty_for_sol(ov_line)
        return max(0.0, ov_line.product_uom_qty - stock - produced)

    def _kc_line_remaining_qty(self, production_line):
        """Saldo pendiente total de la OV para una línea de producción."""
        self.ensure_one()
        groups, _unassigned = self._kc_group_order_lines_by_production_line()
        ov_lines = groups.get(production_line, self.env['sale.order.line'])
        return sum(self._kc_sol_remaining_qty(l) for l in ov_lines)

    @api.depends(
        'order_line', 'order_line.product_id', 'order_line.product_uom_qty',
        'kc_entry_ids', 'kc_entry_ids.state', 'kc_entry_ids.production_line_id',
        'kc_entry_ids.reversal_of_id', 'kc_entry_ids.reversed_by_id',
        'kc_entry_ids.line_ids.qty', 'kc_entry_ids.line_ids.sale_order_line_id',
    )
    def _compute_kc_production_status_ids(self):
        Status = self.env['kc.sale.order.production.status']
        for order in self:
            rows = Status
            groups, unassigned = order._kc_group_order_lines_by_production_line()
            for prod_line, ov_lines in groups.items():
                open_entry = order._kc_get_open_entry_for_line(prod_line)
                remaining = order._kc_line_remaining_qty(prod_line)
                done_entries = order.kc_entry_ids.filtered(
                    lambda e: e.production_line_id == prod_line
                    and e.state == 'done'
                    and not e.is_reversal
                    and not e.reversed_by_id
                )
                if open_entry:
                    status = open_entry.state
                    entry = open_entry
                elif remaining <= 0:
                    status = 'done'
                    entry = done_entries.sorted('id', reverse=True)[:1]
                elif done_entries:
                    status = 'parcial'
                    entry = done_entries.sorted('id', reverse=True)[:1]
                else:
                    status = 'pending'
                    entry = self.env['kc.production.entry']
                product_bits = [
                    '%s x%s' % (l.product_id.display_name, l.product_uom_qty)
                    for l in ov_lines
                ]
                rows |= Status.new({
                    'sale_order_id': order.id,
                    'production_line_id': prod_line.id,
                    'sequence': prod_line.sequence,
                    'product_summary': ', '.join(product_bits),
                    'entry_id': entry.id if entry else False,
                    'status': status,
                })
            if unassigned:
                product_bits = [
                    '%s x%s' % (l.product_id.display_name, l.product_uom_qty)
                    for l in unassigned
                ]
                rows |= Status.new({
                    'sale_order_id': order.id,
                    'product_summary': ', '.join(product_bits),
                    'status': 'none',
                })
            order.kc_production_status_ids = rows

    @api.depends(
        'order_line', 'order_line.product_id', 'order_line.product_uom_qty',
        'kc_entry_ids', 'kc_entry_ids.state',
        'kc_entry_ids.line_ids.qty', 'kc_entry_ids.line_ids.sale_order_line_id',
        'kc_entry_ids.reversal_of_id', 'kc_entry_ids.reversed_by_id',
    )
    def _compute_kc_production_progress_ids(self):
        """Avance por producto para seguimiento del vendedor."""
        # sudo: el vendedor ve el resumen sin necesitar ACL de plan/RP.
        Progress = self.env['kc.sale.order.production.progress']
        Plan = self.env['kc.production.plan.line'].sudo()
        for order in self:
            rows = Progress
            seq = 10
            entries = order.sudo().kc_entry_ids.filtered(
                lambda e: not e.is_reversal and not e.reversed_by_id
            )
            for ov_line in order._kc_get_producible_order_lines():
                plans = Plan.search([
                    ('sale_order_line_id', '=', ov_line.id),
                    ('state', '!=', 'cancelled'),
                ])
                qty_planned = sum(plans.mapped('planned_qty'))
                entry_lines = entries.mapped('line_ids').filtered(
                    lambda l: l.sale_order_line_id == ov_line
                )
                qty_confirmed = sum(
                    entry_lines.filtered(
                        lambda l: l.entry_id.state == 'confirmed'
                    ).mapped('qty')
                )
                qty_validated = sum(
                    entry_lines.filtered(
                        lambda l: l.entry_id.state == 'done'
                    ).mapped('qty')
                )
                qty_ordered = ov_line.product_uom_qty or 0.0
                qty_pending = max(0.0, qty_ordered - qty_validated)
                if qty_validated >= qty_ordered - 1e-6 and qty_ordered:
                    status = 'done'
                elif qty_validated > 0:
                    status = 'parcial'
                elif qty_confirmed > 0:
                    status = 'confirmed'
                elif qty_planned > 0:
                    status = 'planned'
                else:
                    status = 'none'
                tech = getattr(ov_line, 'technical_description', False) or ''
                rows |= Progress.new({
                    'sale_order_id': order.id,
                    'sale_order_line_id': ov_line.id,
                    'sequence': seq,
                    'product_id': ov_line.product_id.id,
                    'technical_description': tech,
                    'qty_ordered': qty_ordered,
                    'qty_planned': qty_planned,
                    'qty_confirmed': qty_confirmed,
                    'qty_validated': qty_validated,
                    'qty_pending': qty_pending,
                    'status': status,
                })
                seq += 10
            order.kc_production_progress_ids = rows

    @api.depends(
        'kc_production_status_ids',
        'kc_production_status_ids.status',
    )
    def _compute_kc_production_counters(self):
        for order in self:
            statuses = order.kc_production_status_ids.filtered(
                lambda s: s.status != 'none')
            required = len(statuses)
            done = len(statuses.filtered(lambda s: s.status == 'done'))
            pending = len(statuses.filtered(
                lambda s: s.status in (
                    'pending', 'draft', 'confirmed', 'parcial',
                )))
            order.kc_production_line_required_count = required
            order.kc_production_line_done_count = done
            order.kc_production_line_pending_count = pending
            order.kc_production_incomplete = bool(required and pending > 0)

    def action_view_kc_lots(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lotes Generados'),
            'res_model': 'stock.lot',
            'view_mode': 'list,form',
            'domain': [('kc_sale_order_id', '=', self.id)],
            'context': {'default_kc_sale_order_id': self.id},
        }

    def action_view_kc_entries(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registros de Producción'),
            'res_model': 'kc.production.entry',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
        }

    def action_view_kc_consumptions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consumos de Materia Prima'),
            'res_model': 'kc.production.consumption',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
        }

    def action_create_kc_production_entry(self):
        """Abre un RP nuevo; el usuario elige la línea en el formulario."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registro de Producción'),
            'res_model': 'kc.production.entry',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_sale_order_id': self.id,
                'default_production_line_id': (
                    self.env['kc.production.entry']._default_production_line_id()),
            },
        }

    def action_create_kc_production_for_line(self):
        """Crea/abre RP para la línea: abre en curso; si solo done con saldo, crea nuevo."""
        self.ensure_one()
        line_id = self.env.context.get('default_production_line_id')
        if not line_id:
            return self.action_create_kc_production_entry()
        prod_line = self.env['kc.production.line'].browse(line_id)
        open_entry = self._kc_get_open_entry_for_line(prod_line)
        if open_entry:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Registro de Producción'),
                'res_model': 'kc.production.entry',
                'view_mode': 'form',
                'res_id': open_entry.id,
                'target': 'current',
            }
        remaining = self._kc_line_remaining_qty(prod_line)
        if remaining <= 0:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin saldo pendiente'),
                    'message': _(
                        'La línea %(line)s de la OV %(so)s ya no tiene cantidad '
                        'pendiente por producir.',
                        line=prod_line.display_name,
                        so=self.display_name,
                    ),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registro de Producción'),
            'res_model': 'kc.production.entry',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_sale_order_id': self.id,
                'default_production_line_id': line_id,
            },
        }
