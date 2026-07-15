# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import format_date


class KcProductionPlanWeekWizard(models.TransientModel):
    """Imprime el plan de la semana laboral (lunes a viernes) por centro."""
    _name = 'kc.production.plan.week.wizard'
    _description = 'Imprimir plan semanal por centro'

    date_ref = fields.Date(
        string='Fecha de referencia',
        required=True,
        default=fields.Date.context_today,
        help='Cualquier día de la semana laboral a imprimir (lun–vie).',
    )
    work_center_id = fields.Many2one(
        comodel_name='kc.work.center',
        string='Centro de Trabajo',
        help='Vacío = todos los centros.',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(string='Desde (lun)', compute='_compute_week_bounds', store=True)
    date_to = fields.Date(string='Hasta (vie)', compute='_compute_week_bounds', store=True)

    @api.depends('date_ref')
    def _compute_week_bounds(self):
        for wiz in self:
            if not wiz.date_ref:
                wiz.date_from = False
                wiz.date_to = False
                continue
            # Lunes = 0 … Domingo = 6
            monday = wiz.date_ref - timedelta(days=wiz.date_ref.weekday())
            friday = monday + timedelta(days=4)
            wiz.date_from = monday
            wiz.date_to = friday

    def _week_dt_bounds(self):
        self.ensure_one()
        start = datetime.combine(self.date_from, time.min)
        end = datetime.combine(self.date_to, time.max)
        return fields.Datetime.to_string(start), fields.Datetime.to_string(end)

    def get_plan_lines(self):
        """Bloques planificados lun–vie, excluye cancelados."""
        self.ensure_one()
        dt_from, dt_to = self._week_dt_bounds()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', '!=', 'cancelled'),
            ('date_planned_start', '>=', dt_from),
            ('date_planned_start', '<=', dt_to),
        ]
        if self.work_center_id:
            domain.append(('work_center_id', '=', self.work_center_id.id))
        return self.env['kc.production.plan.line'].search(
            domain, order='work_center_id, date_planned_start, id')

    def get_lines_by_day_and_center(self):
        """Estructura para el PDF: centro → día → líneas."""
        self.ensure_one()
        grouped = defaultdict(lambda: defaultdict(list))
        for line in self.get_plan_lines():
            day = fields.Datetime.context_timestamp(
                self, line.date_planned_start).date()
            if day < self.date_from or day > self.date_to:
                continue
            grouped[line.work_center_id][day].append(line)
        return grouped

    def action_print(self):
        self.ensure_one()
        if not self.get_plan_lines():
            raise UserError(_(
                'No hay bloques planificados (lun–vie) para el período '
                '%(date_from)s – %(date_to)s.',
                date_from=format_date(self.env, self.date_from),
                date_to=format_date(self.env, self.date_to),
            ))
        return self.env.ref(
            'kc_manual_production.action_report_kc_plan_week'
        ).report_action(self)


class KcProductionPlanMonthWizard(models.TransientModel):
    """Calendario mensual de planificación / confirmado / validado."""
    _name = 'kc.production.plan.month.wizard'
    _description = 'Imprimir calendario mensual de producción'

    year = fields.Integer(
        string='Año',
        required=True,
        default=lambda self: fields.Date.context_today(self).year,
    )
    month = fields.Selection(
        selection=[
            ('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'),
            ('5', 'Mayo'), ('6', 'Junio'), ('7', 'Julio'), ('8', 'Agosto'),
            ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'),
            ('12', 'Diciembre'),
        ],
        string='Mes',
        required=True,
        default=lambda self: str(fields.Date.context_today(self).month),
    )
    work_center_id = fields.Many2one(
        comodel_name='kc.work.center',
        string='Centro de Trabajo',
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Cliente',
    )
    include_planned = fields.Boolean(string='Planificado', default=True)
    include_confirmed = fields.Boolean(string='Confirmado (RP)', default=True)
    include_validated = fields.Boolean(string='Validado (stock)', default=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )

    def _month_bounds(self):
        self.ensure_one()
        month = int(self.month)
        year = self.year
        date_from = fields.Date.from_string('%04d-%02d-01' % (year, month))
        if month == 12:
            date_to = fields.Date.from_string('%04d-12-31' % year)
        else:
            next_first = fields.Date.from_string(
                '%04d-%02d-01' % (year, month + 1))
            date_to = next_first - timedelta(days=1)
        dt_from = fields.Datetime.to_string(datetime.combine(date_from, time.min))
        dt_to = fields.Datetime.to_string(datetime.combine(date_to, time.max))
        return date_from, date_to, dt_from, dt_to

    def get_calendar_rows(self):
        """Filas unificadas: día, estado, cliente, producto, qty, refs."""
        self.ensure_one()
        if not (self.include_planned or self.include_confirmed or self.include_validated):
            raise UserError(_('Seleccione al menos un estado a incluir.'))
        date_from, date_to, dt_from, dt_to = self._month_bounds()
        rows = []

        if self.include_planned:
            domain = [
                ('company_id', '=', self.company_id.id),
                ('state', '!=', 'cancelled'),
                ('date_planned_start', '>=', dt_from),
                ('date_planned_start', '<=', dt_to),
            ]
            if self.work_center_id:
                domain.append(('work_center_id', '=', self.work_center_id.id))
            if self.partner_id:
                domain.append(('sale_order_id.partner_id', '=', self.partner_id.id))
            for plan in self.env['kc.production.plan.line'].search(
                    domain, order='date_planned_start, id'):
                day = fields.Datetime.context_timestamp(
                    self, plan.date_planned_start).date()
                partner = plan.sale_order_id.partner_id if plan.sale_order_id else False
                rows.append({
                    'day': day,
                    'status': _('Planificado'),
                    'status_code': 'planned',
                    'partner': partner.name if partner else '',
                    'product': plan.product_id.display_name,
                    'tech': plan.technical_description or plan.sol_technical_description or '',
                    'qty': plan.planned_qty,
                    'ref': plan.name,
                    'center': plan.work_center_id.name,
                    'sale': plan.sale_order_id.name if plan.sale_order_id else '',
                })

        entry_domain_base = [
            ('company_id', '=', self.company_id.id),
            ('is_reversal', '=', False),
            ('reversed_by_id', '=', False),
            ('date_production', '>=', dt_from),
            ('date_production', '<=', dt_to),
        ]
        if self.work_center_id:
            entry_domain_base.append(('work_center_id', '=', self.work_center_id.id))
        if self.partner_id:
            entry_domain_base.append(('partner_id', '=', self.partner_id.id))

        if self.include_confirmed:
            entries = self.env['kc.production.entry'].search(
                entry_domain_base + [('state', '=', 'confirmed')],
                order='date_production, id')
            for entry in entries:
                day = fields.Datetime.context_timestamp(
                    self, entry.date_production).date()
                for line in entry.line_ids:
                    rows.append({
                        'day': day,
                        'status': _('Confirmado'),
                        'status_code': 'confirmed',
                        'partner': entry.partner_id.name if entry.partner_id else '',
                        'product': line.product_id.display_name,
                        'tech': line.kc_technical_description or '',
                        'qty': line.qty,
                        'ref': entry.name,
                        'center': entry.work_center_id.name if entry.work_center_id else '',
                        'sale': entry.sale_order_id.name if entry.sale_order_id else '',
                    })

        if self.include_validated:
            entries = self.env['kc.production.entry'].search(
                entry_domain_base + [('state', '=', 'done')],
                order='date_production, id')
            for entry in entries:
                day = fields.Datetime.context_timestamp(
                    self, entry.date_production).date()
                for line in entry.line_ids:
                    rows.append({
                        'day': day,
                        'status': _('Validado'),
                        'status_code': 'validated',
                        'partner': entry.partner_id.name if entry.partner_id else '',
                        'product': line.product_id.display_name,
                        'tech': line.kc_technical_description or '',
                        'qty': line.qty,
                        'ref': entry.name,
                        'center': entry.work_center_id.name if entry.work_center_id else '',
                        'sale': entry.sale_order_id.name if entry.sale_order_id else '',
                    })

        rows.sort(key=lambda r: (r['day'], r['status_code'], r['ref'] or '', r['product'] or ''))
        return rows

    def get_rows_by_day(self):
        grouped = defaultdict(list)
        for row in self.get_calendar_rows():
            grouped[row['day']].append(row)
        return grouped

    def action_print(self):
        self.ensure_one()
        if not self.get_calendar_rows():
            raise UserError(_(
                'No hay registros para el mes seleccionado con los filtros indicados.'
            ))
        return self.env.ref(
            'kc_manual_production.action_report_kc_plan_month'
        ).report_action(self)
