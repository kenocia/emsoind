# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, tools, _


class KcProductionBacklog(models.Model):
    """OV pendientes / parciales (vista SQL + stock técnico en Python).

    Solo lista líneas que aún requieren fabricar (OV − stock − producido > 0)
    y que no tienen un plan activo (draft/confirmed/in_progress).
    """
    _name = 'kc.production.backlog'
    _description = 'OV Pendientes / Parciales de Producción'
    _auto = False
    _order = 'sale_order_id, production_line_id, product_id'

    sale_order_id = fields.Many2one('sale.order', string='Orden de Venta', readonly=True)
    sale_order_line_id = fields.Many2one('sale.order.line', string='Línea OV', readonly=True)
    production_line_id = fields.Many2one('kc.production.line', string='Línea de Producción', readonly=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    commitment_date = fields.Datetime(
        string='Fecha de entrega',
        readonly=True,
        help='Fecha de entrega indicada al cliente en la Orden de Venta.',
    )
    technical_description = fields.Text(
        string='Descripción técnica',
        readonly=True,
    )
    ov_qty = fields.Float(string='Cantidad OV', readonly=True, digits='Product Unit of Measure')
    produced_qty = fields.Float(
        string='Ya producido',
        readonly=True,
        digits='Product Unit of Measure',
    )
    raw_pending_qty = fields.Float(
        string='Pendiente (sin stock)',
        readonly=True,
        digits='Product Unit of Measure',
        help='ov_qty − produced_qty (antes de descontar stock compatible).',
    )
    open_rp = fields.Boolean(
        string='RP en curso',
        readonly=True,
        help='Hay un RP en borrador o confirmado para esta línea de OV.',
    )
    open_plan = fields.Boolean(
        string='Plan activo',
        readonly=True,
        help='Hay un bloque de plan en borrador, confirmado o en progreso.',
    )
    planned_open_qty = fields.Float(
        string='Qty planificada abierta',
        readonly=True,
        digits='Product Unit of Measure',
    )
    stock_qty = fields.Float(
        string='Stock compatible',
        compute='_compute_pending_fields',
        digits='Product Unit of Measure',
    )
    pending_qty = fields.Float(
        string='Pendiente',
        compute='_compute_pending_fields',
        digits='Product Unit of Measure',
    )
    status = fields.Selection(
        selection=[
            ('no_requiere', 'No requiere'),
            ('pendiente', 'Pendiente'),
            ('parcial', 'Parcial'),
            ('en_curso', 'En curso'),
            ('planificado', 'Planificado'),
        ],
        string='Estado',
        compute='_compute_pending_fields',
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    sol.id AS id,
                    sol.id AS sale_order_line_id,
                    sol.order_id AS sale_order_id,
                    sol.product_id AS product_id,
                    so.company_id AS company_id,
                    so.partner_id AS partner_id,
                    so.commitment_date AS commitment_date,
                    COALESCE(
                        NULLIF(BTRIM(sol.technical_description), ''),
                        NULLIF(BTRIM(sol.name), '')
                    ) AS technical_description,
                    sol.product_uom_qty AS ov_qty,
                    COALESCE(prod.produced_qty, 0.0) AS produced_qty,
                    GREATEST(sol.product_uom_qty - COALESCE(prod.produced_qty, 0.0), 0.0)
                        AS raw_pending_qty,
                    CASE WHEN COALESCE(open_rp.open_count, 0) > 0 THEN TRUE ELSE FALSE END
                        AS open_rp,
                    CASE WHEN COALESCE(open_plan.open_count, 0) > 0 THEN TRUE ELSE FALSE END
                        AS open_plan,
                    COALESCE(open_plan.planned_qty, 0.0) AS planned_open_qty,
                    pl.id AS production_line_id
                FROM sale_order_line sol
                JOIN sale_order so ON so.id = sol.order_id
                JOIN product_product pp ON pp.id = sol.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN LATERAL (
                    SELECT kpl.id
                    FROM kc_production_line kpl
                    JOIN kc_production_line_product_categ_rel rel
                        ON rel.line_id = kpl.id
                    JOIN product_category allowed ON allowed.id = rel.categ_id
                    JOIN product_category pc ON pc.id = pt.categ_id
                    WHERE kpl.company_id = so.company_id
                      AND kpl.active IS TRUE
                      AND (
                          pc.id = allowed.id
                          OR pc.parent_path LIKE allowed.parent_path || '%%'
                      )
                    ORDER BY length(allowed.parent_path) DESC, kpl.sequence, kpl.id
                    LIMIT 1
                ) pl ON TRUE
                LEFT JOIN LATERAL (
                    SELECT SUM(el.qty) AS produced_qty
                    FROM kc_production_entry_line el
                    JOIN kc_production_entry e ON e.id = el.entry_id
                    WHERE el.sale_order_line_id = sol.id
                      AND e.state = 'done'
                      AND e.reversal_of_id IS NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM kc_production_entry rev
                          WHERE rev.reversal_of_id = e.id
                            AND rev.state = 'done'
                      )
                ) prod ON TRUE
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS open_count
                    FROM kc_production_entry_line el
                    JOIN kc_production_entry e ON e.id = el.entry_id
                    WHERE el.sale_order_line_id = sol.id
                      AND e.state IN ('draft', 'confirmed')
                      AND e.reversal_of_id IS NULL
                ) open_rp ON TRUE
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*) AS open_count,
                        COALESCE(SUM(plan.planned_qty), 0.0) AS planned_qty
                    FROM kc_production_plan_line plan
                    WHERE plan.sale_order_line_id = sol.id
                      AND plan.state IN ('draft', 'confirmed', 'in_progress')
                ) open_plan ON TRUE
                WHERE sol.display_type IS NULL
                  AND so.state IN ('sale', 'done')
                  AND pt.tracking = 'lot'
                  AND pl.id IS NOT NULL
                  AND sol.product_uom_qty > COALESCE(prod.produced_qty, 0.0)
                  AND (
                      -- Producción simple: check en ficha, sin ficha técnica
                      COALESCE(pt.kc_simple_production, FALSE) IS TRUE
                      OR (
                          -- PT técnico con atributos + clave en la OV
                          COALESCE(pt.kc_simple_production, FALSE) IS NOT TRUE
                          AND pt.kc_invoice_detail_mode = 'technical'
                          AND EXISTS (
                              SELECT 1
                              FROM custom_product_technical_attribute_line cptal
                              WHERE cptal.product_tmpl_id = pt.id
                          )
                          AND COALESCE(NULLIF(BTRIM(sol.technical_key), ''), '') <> ''
                      )
                  )
            )
        """ % self._table)

    @api.depends('sale_order_line_id', 'ov_qty', 'produced_qty', 'open_rp', 'open_plan')
    def _compute_pending_fields(self):
        for rec in self:
            stock = 0.0
            sol = rec.sale_order_line_id
            if sol and hasattr(sol, '_kc_get_compatible_available_qty'):
                stock = sol._kc_get_compatible_available_qty() or 0.0
            pending = max(0.0, (rec.ov_qty or 0.0) - stock - (rec.produced_qty or 0.0))
            rec.stock_qty = stock
            rec.pending_qty = pending
            if pending <= 0:
                rec.status = 'no_requiere'
            elif rec.open_plan:
                rec.status = 'planificado'
            elif rec.open_rp:
                rec.status = 'en_curso'
            elif (rec.produced_qty or 0.0) > 0:
                rec.status = 'parcial'
            else:
                rec.status = 'pendiente'

    def _kc_filter_needs_production(self, records):
        """Excluye cubiertos por stock/producción o con plan activo."""
        return records.filtered(
            lambda r: (r.pending_qty or 0.0) > 1e-6 and not r.open_plan
        )

    @api.model
    def search_fetch(self, domain, field_names, offset=0, limit=None, order=None):
        """Filtra en Python tras el SQL (stock compatible no está en la vista).

        No sobreescribir search(): en Odoo 18 search() → search_fetch() y
        provoca recursión infinita.
        """
        records = super().search_fetch(
            domain, field_names, offset=0, limit=None, order=order)
        records = self._kc_filter_needs_production(records)
        if offset:
            records = records[offset:]
        if limit is not None:
            records = records[:limit]
        return records

    @api.model
    def search_count(self, domain, limit=None):
        records = super().search_fetch(
            domain,
            ['ov_qty', 'produced_qty', 'sale_order_line_id', 'open_rp', 'open_plan'],
            offset=0,
            limit=None,
        )
        count = len(self._kc_filter_needs_production(records))
        if limit is not None:
            return min(count, limit)
        return count

    def write(self, vals):
        """Vista SQL: no persiste. Evita error de ACL si algo intenta escribir."""
        return True

    def unlink(self):
        return True

    def action_open_mass_plan_wizard(self):
        """Abre el wizard de planificación masiva (Acciones → Planificar selección).

        Se crea en servidor con las líneas ya persistidas: el cliente no reenvía
        bien campos readonly del O2M al pulsar Confirmar.
        """
        Wizard = self.env['kc.production.backlog.mass.plan.wizard']
        vals = Wizard._kc_prepare_wizard_vals(self)
        wizard = Wizard.create(vals)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Planificar selección'),
            'res_model': 'kc.production.backlog.mass.plan.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'kc.production.backlog',
                'active_ids': self.ids,
                'active_id': self[:1].id,
            },
        }

    def action_planificar(self):
        """Abre un bloque de planificación con qty a producir (≤ OV, ≤ pendiente real)."""
        self.ensure_one()
        # Invalidar para recalcular stock; no llamar al compute a mano (haría write).
        self.invalidate_recordset(
            ['stock_qty', 'pending_qty', 'status', 'open_plan', 'planned_open_qty'])
        if self.open_plan:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Ya planificado'),
                    'message': _(
                        'Esta línea ya tiene un bloque de planificación activo. '
                        'Revise Operaciones → Planificación o cancele el plan '
                        'antes de volver a planificar.'
                    ),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        qty_to_plan = self.pending_qty
        if qty_to_plan <= 0:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin cantidad a producir'),
                    'message': _(
                        'Esta línea ya está cubierta por stock compatible '
                        'o por RP validados. No requiere planificar.'
                    ),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        # Tope: nunca más que la cantidad de la OV ni que el saldo sin stock.
        ov_cap = self.ov_qty or 0.0
        raw_cap = self.raw_pending_qty or 0.0
        qty_to_plan = min(qty_to_plan, ov_cap, raw_cap)
        if qty_to_plan <= 0:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin cantidad a producir'),
                    'message': _('La cantidad de la OV ya está cubierta.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        Plan = self.env['kc.production.plan.line']
        if not Plan._kc_sol_is_plannable(self.sale_order_line_id):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Línea no planificable'),
                    'message': _(
                        'Use un producto técnico con clave en la OV, o active '
                        '"Producción simple" en la ficha del producto.'
                    ),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        center = self.env['kc.work.center'].search([
            ('production_line_id', '=', self.production_line_id.id),
            ('state', '=', 'active'),
            ('active', '=', True),
        ], order='sequence, id', limit=1)
        start = fields.Datetime.now()
        end = start + timedelta(days=1)
        sol = self.sale_order_line_id
        tech_desc = self.technical_description or getattr(sol, 'technical_description', False) or False
        if not tech_desc:
            tech_desc = self.env['kc.production.entry']._kc_description_from_sale_line(sol)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Planificar producción'),
            'res_model': 'kc.production.plan.line',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
            'context': {
                'default_origin_type': 'sale_order',
                'default_work_center_id': center.id if center else False,
                'default_product_id': self.product_id.id,
                'default_sale_order_id': self.sale_order_id.id,
                'default_sale_order_line_id': self.sale_order_line_id.id,
                'default_technical_key': sol.technical_key,
                'default_technical_description': tech_desc,
                'default_planned_qty': qty_to_plan,
                'default_date_planned_start': start,
                'default_date_planned_end': end,
                'form_view_initial_mode': 'edit',
            },
        }
