# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class KcProductionBacklogMassPlanWizard(models.TransientModel):
    """Planificación masiva completa: mismo centro y fechas para la selección."""
    _name = 'kc.production.backlog.mass.plan.wizard'
    _description = 'Planificar selección de OV pendientes'

    production_line_id = fields.Many2one(
        comodel_name='kc.production.line',
        string='Línea de Producción',
        required=True,
        readonly=True,
    )
    work_center_id = fields.Many2one(
        comodel_name='kc.work.center',
        string='Centro de Trabajo',
        required=True,
        domain="[('production_line_id', '=', production_line_id), "
               "('state', '=', 'active'), ('active', '=', True)]",
    )
    date_planned_start = fields.Datetime(
        string='Inicio planificado',
        required=True,
        default=fields.Datetime.now,
    )
    date_planned_end = fields.Datetime(
        string='Fin planificado',
        required=True,
        default=lambda self: fields.Datetime.now() + timedelta(days=1),
    )
    line_ids = fields.One2many(
        comodel_name='kc.production.backlog.mass.plan.wizard.line',
        inverse_name='wizard_id',
        string='Líneas a planificar',
    )
    line_count = fields.Integer(compute='_compute_line_count')

    @api.depends('line_ids', 'line_ids.pending_qty', 'line_ids.product_id')
    def _compute_line_count(self):
        for wiz in self:
            wiz.line_count = len(wiz._kc_valid_lines())

    def _kc_valid_lines(self):
        """Ignora filas incompletas (sin producto / sin qty)."""
        self.ensure_one()
        return self.line_ids.filtered(
            lambda l: l.product_id
            and l.sale_order_line_id
            and float_compare(l.pending_qty or 0.0, 0.0, precision_digits=4) > 0
        )

    @api.model
    def _kc_plan_qty(self, backlog):
        return min(
            backlog.pending_qty or 0.0,
            backlog.ov_qty or 0.0,
            backlog.raw_pending_qty or 0.0,
        )

    @api.model
    def _kc_prepare_wizard_vals(self, backlogs):
        """Valores completos del wizard (líneas incluidas) para create en servidor."""
        backlogs.invalidate_recordset(
            ['stock_qty', 'pending_qty', 'status', 'open_rp', 'open_plan',
             'raw_pending_qty', 'planned_open_qty'])
        self._kc_validate_selection(backlogs)
        production_line = backlogs.mapped('production_line_id')
        vals = {
            'production_line_id': production_line.id,
            'date_planned_start': fields.Datetime.now(),
            'date_planned_end': fields.Datetime.now() + timedelta(days=1),
        }
        center = self.env['kc.work.center'].search([
            ('production_line_id', '=', production_line.id),
            ('state', '=', 'active'),
            ('active', '=', True),
        ], order='sequence, id', limit=1)
        if center:
            vals['work_center_id'] = center.id
        lines = []
        for bl in backlogs:
            qty = self._kc_plan_qty(bl)
            if float_compare(qty, 0.0, precision_digits=4) <= 0:
                continue
            sol = bl.sale_order_line_id
            if not sol or not bl.product_id:
                continue
            tech = bl.technical_description or getattr(
                sol, 'technical_description', False) or False
            lines.append((0, 0, {
                'backlog_id': bl.id,
                'sale_order_id': bl.sale_order_id.id,
                'sale_order_line_id': sol.id,
                'partner_id': bl.partner_id.id,
                'product_id': bl.product_id.id,
                'technical_description': tech,
                'technical_key': (sol.technical_key or '').strip() or False,
                'ov_qty': bl.ov_qty,
                'pending_qty': qty,
            }))
        if not lines:
            raise UserError(_(
                'Ninguna línea de la selección tiene cantidad pendiente '
                'planificable.'
            ))
        vals['line_ids'] = lines
        return vals

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids') or []
        if not active_ids:
            return res
        backlogs = self.env['kc.production.backlog'].browse(active_ids)
        prepared = self._kc_prepare_wizard_vals(backlogs)
        for key, value in prepared.items():
            if not fields_list or key in fields_list:
                res[key] = value
        return res

    @api.model
    def _kc_validate_selection(self, backlogs):
        if not backlogs:
            raise UserError(_('Seleccione al menos una línea del backlog.'))
        lines = backlogs.mapped('production_line_id')
        if len(lines) != 1:
            raise UserError(_(
                'Todas las líneas seleccionadas deben ser de la misma '
                'línea de producción. Selección actual: %s'
            ) % ', '.join(lines.mapped('name') or [_('sin línea')]))
        open_rp = backlogs.filtered(lambda b: b.open_rp)
        if open_rp:
            refs = ', '.join(
                '%s / %s' % (b.sale_order_id.name, b.product_id.display_name)
                for b in open_rp[:5]
            )
            raise UserError(_(
                'No se puede planificar en masa: hay RP en curso en:\n%s\n'
                'Cierre o valide esos RP antes de continuar.'
            ) % refs)
        open_plan = backlogs.filtered(lambda b: b.open_plan)
        if open_plan:
            refs = ', '.join(
                '%s / %s' % (b.sale_order_id.name, b.product_id.display_name)
                for b in open_plan[:5]
            )
            raise UserError(_(
                'No se puede planificar en masa: ya hay plan activo en:\n%s\n'
                'Cancele esos planes o quítelos de la selección.'
            ) % refs)
        no_pending = backlogs.filtered(
            lambda b: float_compare(
                self._kc_plan_qty(b), 0.0, precision_digits=4) <= 0
        )
        if no_pending and len(no_pending) == len(backlogs):
            raise UserError(_(
                'Ninguna línea seleccionada tiene cantidad pendiente '
                'de producir.'
            ))
        if no_pending:
            raise UserError(_(
                'Hay líneas sin cantidad pendiente de producir (stock o '
                'producción ya cubren el saldo). Quite esas filas de la selección.'
            ))

    def action_print_preview(self):
        """PDF del preview (sin crear planes)."""
        self.ensure_one()
        if not self._kc_valid_lines():
            raise UserError(_('No hay líneas válidas para imprimir.'))
        if not self.work_center_id:
            raise UserError(_('Seleccione el centro de trabajo antes de imprimir.'))
        return self.env.ref(
            'kc_manual_production.action_report_kc_mass_plan_preview'
        ).report_action(self)

    def action_confirm_plans(self):
        self.ensure_one()
        valid = self._kc_valid_lines()
        # Fallback: si el cliente no persistió el O2M readonly, recrear desde contexto.
        if not valid:
            active_ids = self.env.context.get('active_ids') or []
            if active_ids and self.env.context.get('active_model') == 'kc.production.backlog':
                backlogs = self.env['kc.production.backlog'].browse(active_ids)
                prepared = self._kc_prepare_wizard_vals(backlogs)
                self.line_ids.unlink()
                self.write({'line_ids': prepared['line_ids']})
                valid = self._kc_valid_lines()
        if not valid:
            raise UserError(_('No hay líneas válidas para planificar.'))
        if self.date_planned_end <= self.date_planned_start:
            raise UserError(_('El fin planificado debe ser posterior al inicio.'))
        if self.work_center_id.production_line_id != self.production_line_id:
            raise UserError(_(
                'El centro de trabajo debe pertenecer a la línea "%s".'
            ) % self.production_line_id.display_name)
        if self.work_center_id.state != 'active':
            raise UserError(_(
                'El centro "%s" no está activo.'
            ) % self.work_center_id.display_name)

        Plan = self.env['kc.production.plan.line']
        Entry = self.env['kc.production.entry']
        created = Plan.browse()
        for line in valid:
            qty = line.pending_qty
            sol = line.sale_order_line_id
            if not Plan._kc_sol_is_plannable(sol):
                raise UserError(_(
                    'La línea de OV %(line)s no es planificable. Use un producto '
                    'técnico con clave, o active "Producción simple" en la ficha '
                    'del producto.',
                    line=sol.display_name or sol.id,
                ))
            tech_key = (
                (line.technical_key or getattr(sol, 'technical_key', None) or '')
                .strip()
            ) or False
            tech_desc = line.technical_description or False
            if not tech_desc:
                tech_desc = getattr(sol, 'technical_description', False) or False
            if not tech_desc:
                tech_desc = Entry._kc_description_from_sale_line(sol)
            vals = {
                'origin_type': 'sale_order',
                'work_center_id': self.work_center_id.id,
                'sale_order_id': line.sale_order_id.id,
                'sale_order_line_id': sol.id,
                'product_id': line.product_id.id,
                'technical_key': tech_key,
                'technical_description': tech_desc,
                'planned_qty': qty,
                'date_planned_start': self.date_planned_start,
                'date_planned_end': self.date_planned_end,
                'state': 'draft',
            }
            # Misma fecha/centro a propósito: permite solape (Gantt marca sobrecarga).
            plan = Plan.with_context(kc_allow_plan_overlap=True).create(vals)
            plan.with_context(kc_allow_plan_overlap=True).action_confirm()
            created |= plan

        return {
            'type': 'ir.actions.act_window',
            'name': _('Planificación creada'),
            'res_model': 'kc.production.plan.line',
            'view_mode': 'gantt,list,form',
            'domain': [('id', 'in', created.ids)],
            'context': {
                'search_default_group_center': 1,
                'active_ids': created.ids,
            },
            'target': 'current',
        }


class KcProductionBacklogMassPlanWizardLine(models.TransientModel):
    _name = 'kc.production.backlog.mass.plan.wizard.line'
    _description = 'Línea de planificación masiva (preview)'

    wizard_id = fields.Many2one(
        comodel_name='kc.production.backlog.mass.plan.wizard',
        required=True,
        ondelete='cascade',
    )
    # ID del backlog (= sale.order.line); el backlog es vista SQL.
    backlog_id = fields.Integer(string='Backlog ID', required=True)
    sale_order_id = fields.Many2one('sale.order', string='Orden de Venta', readonly=True)
    sale_order_line_id = fields.Many2one('sale.order.line', string='Línea OV', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    technical_description = fields.Text(string='Descripción técnica', readonly=True)
    technical_key = fields.Char(string='Clave técnica', readonly=True)
    ov_qty = fields.Float(string='Cantidad OV', readonly=True, digits='Product Unit of Measure')
    pending_qty = fields.Float(
        string='A planificar (completo)',
        readonly=True,
        digits='Product Unit of Measure',
        help='Cantidad pendiente completa de la línea (no editable en masivo).',
    )
