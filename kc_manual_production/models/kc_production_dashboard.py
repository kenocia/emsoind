# -*- coding: utf-8 -*-
from datetime import timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError
from odoo.tools.float_utils import float_compare


class KcProductionDashboard(models.Model):
    """Servicio OWL: Resumen de Producción (Operación / Planificación / Cumplimiento)."""
    _name = 'kc.production.dashboard'
    _description = 'Resumen de Producción'

    def _check_dashboard_access(self):
        user = self.env.user
        allowed = (
            'kc_manual_production.kc_production_group_manager',
            'kc_manual_production.kc_production_group_bodega',
            'kc_manual_production.kc_production_group_user',
            'kc_manual_production.kc_production_group_planner',
            'stock.group_stock_manager',
        )
        if not any(user.has_group(g) for g in allowed):
            raise AccessError(_(
                "No tiene permiso para acceder al Resumen de Producción."))

    def _kc_user_is_operational_manager(self):
        user = self.env.user
        return (
            user.has_group('kc_manual_production.kc_production_group_manager')
            or user.has_group('stock.group_stock_manager')
            or user.has_group('kc_manual_production.kc_production_group_bodega')
        )

    @api.model
    def _kc_get_user_line_ids(self):
        Line = self.env['kc.production.line']
        if self._kc_user_is_operational_manager():
            return Line.search([
                ('company_id', '=', self.env.company.id),
                ('active', '=', True),
            ]).ids
        return Line.search([
            ('company_id', '=', self.env.company.id),
            ('active', '=', True),
            ('user_ids', 'in', self.env.user.id),
        ]).ids

    @api.model
    def get_production_lines(self):
        self._check_dashboard_access()
        line_ids = self._kc_get_user_line_ids()
        lines = self.env['kc.production.line'].browse(line_ids).sorted(
            key=lambda l: (l.sequence, l.name))
        return [{'id': line.id, 'name': line.name, 'code': line.code or ''} for line in lines]

    @api.model
    def get_work_centers(self, production_line_id=False):
        """Centros activos visibles según líneas del usuario / filtro de línea."""
        self._check_dashboard_access()
        line_ids = self._kc_get_user_line_ids()
        if production_line_id:
            if production_line_id not in line_ids:
                return []
            line_ids = [production_line_id]
        centers = self.env['kc.work.center'].search([
            ('production_line_id', 'in', line_ids or [0]),
            ('active', '=', True),
        ], order='sequence, name')
        return [{
            'id': c.id,
            'name': c.display_name or c.name,
            'production_line_id': c.production_line_id.id,
            'state': c.state,
        } for c in centers]

    @api.model
    def get_date_range(self, range_type):
        self._check_dashboard_access()
        hoy = fields.Date.context_today(self)
        if range_type == 'today':
            date_from = hoy
            date_to = hoy
        elif range_type == 'week':
            date_from = hoy - timedelta(days=hoy.weekday())
            date_to = date_from + timedelta(days=6)
        else:
            date_from = hoy.replace(day=1)
            date_to = date_from + relativedelta(months=1, days=-1)
        return {
            'date_from': fields.Date.to_string(date_from),
            'date_to': fields.Date.to_string(date_to),
        }

    def _get_datetime_bounds(self, date_from, date_to):
        tz_from = fields.Date.from_string(date_from)
        tz_to = fields.Date.from_string(date_to)
        start_naive = fields.Datetime.from_string(f"{tz_from} 00:00:00")
        end_naive = fields.Datetime.from_string(f"{tz_to} 23:59:59")
        start_utc = fields.Datetime.to_string(self._localize_to_utc(start_naive))
        end_utc = fields.Datetime.to_string(self._localize_to_utc(end_naive))
        return start_utc, end_utc

    def _localize_to_utc(self, naive_dt):
        tz_name = self.env.user.tz or 'UTC'
        user_tz = pytz.timezone(tz_name)
        localized = user_tz.localize(naive_dt)
        return localized.astimezone(pytz.UTC).replace(tzinfo=None)

    @api.model
    def _kc_status_color(self, value, green, amber_max, higher_is_worse=True):
        if higher_is_worse:
            if value <= green:
                return 'green'
            if value <= amber_max:
                return 'amber'
            return 'red'
        if value >= green:
            return 'green'
        if value >= amber_max:
            return 'amber'
        return 'red'

    @api.model
    def _kc_get_active_lines(self, production_line_id=False, work_center_id=False):
        line_ids = self._kc_get_user_line_ids()
        if production_line_id:
            if production_line_id not in line_ids:
                return self.env['kc.production.line']
            lines = self.env['kc.production.line'].browse(production_line_id)
        else:
            lines = self.env['kc.production.line'].browse(line_ids)
        if work_center_id:
            center = self.env['kc.work.center'].browse(work_center_id)
            if not center.exists() or center.production_line_id.id not in lines.ids:
                return self.env['kc.production.line']
            lines = center.production_line_id
        return lines.sorted(key=lambda l: (l.sequence, l.name))

    @api.model
    def _kc_iter_dates(self, date_from, date_to):
        cursor = fields.Date.from_string(date_from)
        end = fields.Date.from_string(date_to)
        while cursor <= end:
            yield cursor
            cursor += timedelta(days=1)

    @api.model
    def _kc_day_rp_stats(self, line, day, work_center_id=False):
        range_from, range_to = self._get_datetime_bounds(
            fields.Date.to_string(day), fields.Date.to_string(day))
        domain = [
            ('state', '=', 'done'),
            ('production_line_id', '=', line.id),
            ('date_production', '>=', range_from),
            ('date_production', '<=', range_to),
        ]
        if work_center_id:
            domain.append(('work_center_id', '=', work_center_id))
        entries = self.env['kc.production.entry'].search(domain)
        return {
            'rp_count': len(entries),
            'units': sum(entries.mapped('line_ids.qty')),
        }

    @api.model
    def _kc_range_rp_stats(self, lines, date_from, date_to, work_center_id=False):
        """RP validados y unidades PT en el rango completo (valor del KPI)."""
        range_from, range_to = self._get_datetime_bounds(date_from, date_to)
        domain = [
            ('state', '=', 'done'),
            ('production_line_id', 'in', lines.ids or [0]),
            ('date_production', '>=', range_from),
            ('date_production', '<=', range_to),
        ]
        if work_center_id:
            domain.append(('work_center_id', '=', work_center_id))
        entries = self.env['kc.production.entry'].search(domain)
        return {
            'rp_count': len(entries),
            'units': sum(entries.mapped('line_ids.qty')),
        }

    def _kc_day_daily_cmp(self, line, day):
        Consumption = self.env['kc.production.consumption']
        return Consumption._kc_find_daily_cmp(line, day, company=line.company_id)

    @api.model
    def _kc_cell_status(self, line, day, work_center_id=False):
        Consumption = self.env['kc.production.consumption']
        cmp = Consumption._kc_find_daily_cmp(line, day, company=line.company_id)
        if cmp and cmp.state == 'done':
            return 'closed', cmp
        if cmp and cmp.state in Consumption._kc_daily_open_states():
            return 'open', cmp
        rp = self._kc_day_rp_stats(line, day, work_center_id=work_center_id)
        if rp['rp_count']:
            return 'orphan', cmp
        return 'idle', cmp

    @api.model
    def _kc_operational_status(self, line, today, cmp_today, blocking_cmp, orphan_in_range):
        Consumption = self.env['kc.production.consumption']
        if blocking_cmp and blocking_cmp.consumption_date < today:
            return 'blocked', _('Bloqueado')
        if cmp_today and cmp_today.state == 'done':
            return 'ok', _('Al día')
        if cmp_today and cmp_today.state in Consumption._kc_daily_open_states():
            return 'open', _('Abierto')
        if orphan_in_range:
            return 'orphan', _('Sin cerrar')
        return 'idle', _('Sin actividad')

    @api.model
    def _kc_build_alerts(self, lines, today, work_center_id=False):
        Consumption = self.env['kc.production.consumption']
        alerts = []
        for line in lines:
            blocking = Consumption._kc_find_blocking_daily_cmp(line, today, company=line.company_id)
            if blocking:
                alerts.append({
                    'id': f'block_{line.id}_{blocking.id}',
                    'type': 'blocking',
                    'severity': 'critical',
                    'line_id': line.id,
                    'line_name': line.name,
                    'message': _(
                        'Línea %(line)s: no puede abrir el consumo del %(target)s '
                        'hasta validar o cancelar %(cmp)s del %(date)s.',
                        line=line.name,
                        target=fields.Date.to_string(today),
                        cmp=blocking.display_name,
                        date=fields.Date.to_string(blocking.consumption_date),
                    ),
                    'action': 'open_cmp',
                    'res_id': blocking.id,
                    'cmp_name': blocking.display_name,
                })
            yesterday = today - timedelta(days=1)
            rp_y = self._kc_day_rp_stats(line, yesterday, work_center_id=work_center_id)
            cmp_y = self._kc_day_daily_cmp(line, yesterday)
            if rp_y['rp_count'] and (not cmp_y or cmp_y.state != 'done'):
                alerts.append({
                    'id': f'orphan_{line.id}_{yesterday}',
                    'type': 'orphan_day',
                    'severity': 'warning',
                    'line_id': line.id,
                    'line_name': line.name,
                    'message': _(
                        'Línea %(line)s: hubo %(count)s OP validada(s) el %(date)s '
                        'sin consumo diario validado.',
                        line=line.name,
                        count=rp_y['rp_count'],
                        date=fields.Date.to_string(yesterday),
                    ),
                    'action': 'create_cmp',
                    'res_id': False,
                    'consumption_date': fields.Date.to_string(yesterday),
                })
            stale = Consumption.search([
                ('consumption_mode', '=', 'daily'),
                ('production_line_id', '=', line.id),
                ('state', 'in', Consumption._kc_daily_open_states()),
                ('consumption_date', '<', today - timedelta(days=1)),
            ], order='consumption_date asc', limit=1)
            if stale:
                alerts.append({
                    'id': f'stale_{stale.id}',
                    'type': 'stale_cmp',
                    'severity': 'warning',
                    'line_id': line.id,
                    'line_name': line.name,
                    'message': _(
                        '%(cmp)s (%(line)s) del %(date)s sigue sin validar.',
                        cmp=stale.display_name,
                        line=line.name,
                        date=fields.Date.to_string(stale.consumption_date),
                    ),
                    'action': 'open_cmp',
                    'res_id': stale.id,
                    'cmp_name': stale.display_name,
                })
        return alerts[:8]

    def _kc_user_can_create_daily_cmp(self):
        user = self.env.user
        return (
            user.has_group('kc_manual_production.kc_production_group_bodega')
            or user.has_group('kc_manual_production.kc_production_group_manager')
            or user.has_group('stock.group_stock_manager')
        )

    @api.model
    def action_create_daily_cmp(self, production_line_id, consumption_date):
        self._check_dashboard_access()
        if not self._kc_user_can_create_daily_cmp():
            raise AccessError(_(
                'Solo bodega o gerencia puede crear consumos diarios.'))
        return self.env['kc.production.consumption'].action_create_daily_cmp(
            production_line_id, consumption_date)

    @api.model
    def action_open_cmp(self, cmp_id):
        self._check_dashboard_access()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consumo de Componentes'),
            'res_model': 'kc.production.consumption',
            'view_mode': 'form',
            'res_id': cmp_id,
            'target': 'current',
        }

    @api.model
    def _kc_plan_domain(self, lines, date_from, date_to, work_center_id=False):
        """Planes cuyo intervalo se solapa con el rango (excluye cancelados)."""
        range_from, range_to = self._get_datetime_bounds(date_from, date_to)
        domain = [
            ('state', '!=', 'cancelled'),
            ('production_line_id', 'in', lines.ids or [0]),
            ('date_planned_start', '<=', range_to),
            ('date_planned_end', '>=', range_from),
        ]
        if work_center_id:
            domain.append(('work_center_id', '=', work_center_id))
        return domain

    @api.model
    def action_open_kpi(self, kpi_type, date_from, date_to,
                        production_line_id=False, work_center_id=False):
        self._check_dashboard_access()
        range_from, range_to = self._get_datetime_bounds(date_from, date_to)
        lines = self._kc_get_active_lines(production_line_id, work_center_id)
        line_ids = lines.ids
        Consumption = self.env['kc.production.consumption']
        Plan = self.env['kc.production.plan.line']

        if kpi_type == 'lines_closed':
            closed_line_ids = []
            today = fields.Date.context_today(self)
            for line in lines:
                cmp = Consumption._kc_find_daily_cmp(
                    line, today, company=line.company_id, states=['done'])
                if cmp:
                    closed_line_ids.append(line.id)
            missing_ids = [lid for lid in line_ids if lid not in closed_line_ids]
            return {
                'type': 'ir.actions.act_window',
                'name': _('Líneas sin cierre hoy'),
                'res_model': 'kc.production.line',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': [('id', 'in', missing_ids or [0])],
                'target': 'current',
            }

        if kpi_type == 'cmp_open':
            domain = [
                ('consumption_mode', '=', 'daily'),
                ('state', 'in', Consumption._kc_daily_open_states()),
                ('consumption_date', '>=', date_from),
                ('consumption_date', '<=', date_to),
                ('production_line_id', 'in', line_ids or [0]),
            ]
            return {
                'type': 'ir.actions.act_window',
                'name': _('Consumos diarios abiertos'),
                'res_model': 'kc.production.consumption',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': domain,
                'target': 'current',
            }

        if kpi_type == 'lines_blocked':
            blocked_cmp_ids = []
            today = fields.Date.context_today(self)
            for line in lines:
                blocking = Consumption._kc_find_blocking_daily_cmp(
                    line, today, company=line.company_id)
                if blocking:
                    blocked_cmp_ids.append(blocking.id)
            return {
                'type': 'ir.actions.act_window',
                'name': _('Consumos que bloquean operación'),
                'res_model': 'kc.production.consumption',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': [('id', 'in', blocked_cmp_ids or [0])],
                'target': 'current',
            }

        if kpi_type in ('rp_period', 'rp_today', 'units_today', 'units_period'):
            domain = [
                ('state', '=', 'done'),
                ('date_production', '>=', range_from),
                ('date_production', '<=', range_to),
                ('production_line_id', 'in', line_ids or [0]),
            ]
            if work_center_id:
                domain.append(('work_center_id', '=', work_center_id))
            return {
                'type': 'ir.actions.act_window',
                'name': _('Órdenes de Producción'),
                'res_model': 'kc.production.entry',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': domain,
                'target': 'current',
            }

        if kpi_type == 'rp_queue':
            domain = [
                ('state', '=', 'confirmed'),
                ('production_line_id', 'in', line_ids or [0]),
            ]
            if work_center_id:
                domain.append(('work_center_id', '=', work_center_id))
            return {
                'type': 'ir.actions.act_window',
                'name': _('Órdenes pendientes de validar'),
                'res_model': 'kc.production.entry',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': domain,
                'context': {'search_default_filter_confirmed': 1},
                'target': 'current',
            }

        if kpi_type == 'orphan_days':
            domain = [
                ('consumption_mode', '=', 'daily'),
                ('state', 'in', Consumption._kc_daily_open_states()),
                ('production_line_id', 'in', line_ids or [0]),
            ]
            return {
                'type': 'ir.actions.act_window',
                'name': _('Consumos diarios pendientes'),
                'res_model': 'kc.production.consumption',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': domain,
                'target': 'current',
            }

        if kpi_type in ('plans_active', 'plans_delayed', 'plans_overloaded', 'compliance'):
            domain = self._kc_plan_domain(lines, date_from, date_to, work_center_id)
            if kpi_type == 'plans_active':
                domain = domain + [('state', 'in', ('draft', 'confirmed', 'in_progress'))]
                name = _('Planes activos')
            elif kpi_type == 'plans_delayed':
                domain = domain + [('is_delayed', '=', True)]
                name = _('Planes retrasados')
            elif kpi_type == 'plans_overloaded':
                domain = domain + [('is_overloaded', '=', True)]
                name = _('Planes en sobrecarga')
            else:
                name = _('Planes del período')
            return {
                'type': 'ir.actions.act_window',
                'name': name,
                'res_model': 'kc.production.plan.line',
                'view_mode': 'gantt,list,form',
                'views': [[False, 'gantt'], [False, 'list'], [False, 'form']],
                'domain': domain,
                'target': 'current',
            }

        if kpi_type == 'centers_maintenance':
            domain = [
                ('production_line_id', 'in', line_ids or [0]),
                ('state', '=', 'maintenance'),
                ('active', '=', True),
            ]
            if work_center_id:
                domain.append(('id', '=', work_center_id))
            return {
                'type': 'ir.actions.act_window',
                'name': _('Centros en mantenimiento'),
                'res_model': 'kc.work.center',
                'view_mode': 'list,form',
                'views': [[False, 'list'], [False, 'form']],
                'domain': domain,
                'target': 'current',
            }

        if kpi_type == 'backlog':
            return {
                'type': 'ir.actions.act_window',
                'name': _('Órdenes Pendientes de Producir'),
                'res_model': 'kc.production.backlog',
                'view_mode': 'list,kanban',
                'views': [[False, 'list'], [False, 'kanban']],
                'domain': [('production_line_id', 'in', line_ids or [0])],
                'target': 'current',
            }

        raise AccessError(_('Tipo de KPI no reconocido.'))

    @api.model
    def action_open_plan(self, plan_id):
        self._check_dashboard_access()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Planificación'),
            'res_model': 'kc.production.plan.line',
            'view_mode': 'form',
            'res_id': plan_id,
            'views': [[False, 'form']],
            'target': 'current',
        }

    @api.model
    def get_dashboard_data(self, date_from, date_to,
                           production_line_id=False, work_center_id=False):
        self._check_dashboard_access()
        lines = self._kc_get_active_lines(production_line_id, work_center_id)
        today = fields.Date.context_today(self)
        d_from = fields.Date.from_string(date_from)
        d_to = fields.Date.from_string(date_to)
        show_calendar = (d_to - d_from).days >= 1 or d_from != d_to

        operation = self._kc_build_operation(
            lines, date_from, date_to, today, show_calendar, d_from, d_to,
            work_center_id=work_center_id)
        planning = self._kc_build_planning(
            lines, date_from, date_to, work_center_id)
        compliance = self._kc_build_compliance(
            lines, date_from, date_to, work_center_id)

        return {
            'meta': {
                'date_from': date_from,
                'date_to': date_to,
                'production_line_id': production_line_id or False,
                'work_center_id': work_center_id or False,
                'active_lines_count': len(lines),
                'show_calendar': show_calendar,
                'can_create_daily_cmp': self._kc_user_can_create_daily_cmp(),
            },
            'operation': operation,
            'planning': planning,
            'compliance': compliance,
            # Compat hacia atrás (tests / scripts antiguos)
            'kpis': operation['kpis'],
            'alerts': operation['alerts'],
            'line_status': operation['line_status'],
            'compliance_calendar': operation['compliance_calendar'],
            'chart_data': operation['chart_data'],
        }

    @api.model
    def _kc_build_operation(self, lines, date_from, date_to, today,
                            show_calendar, d_from, d_to, work_center_id=False):
        Consumption = self.env['kc.production.consumption']
        lines_closed_today = 0
        lines_blocked_count = 0
        orphan_days_count = 0
        line_status = []
        labels = []
        units_series = []
        closed_series = []
        orphan_markers = []

        open_cmps = Consumption.search([
            ('consumption_mode', '=', 'daily'),
            ('state', 'in', Consumption._kc_daily_open_states()),
            ('consumption_date', '>=', date_from),
            ('consumption_date', '<=', date_to),
            ('production_line_id', 'in', lines.ids or [0]),
        ])

        rp_queue_domain = [
            ('state', '=', 'confirmed'),
            ('production_line_id', 'in', lines.ids or [0]),
        ]
        if work_center_id:
            rp_queue_domain.append(('work_center_id', '=', work_center_id))
        rp_queue = self.env['kc.production.entry'].search_count(rp_queue_domain)

        for day in self._kc_iter_dates(date_from, date_to):
            labels.append(fields.Date.to_string(day))
            day_units = 0.0
            day_closed = 0
            day_orphan = 0
            for line in lines:
                rp = self._kc_day_rp_stats(line, day, work_center_id=work_center_id)
                day_units += rp['units']
                status, cmp = self._kc_cell_status(
                    line, day, work_center_id=work_center_id)
                if status == 'closed':
                    day_closed += 1
                elif status == 'orphan':
                    day_orphan += 1
                    orphan_days_count += 1
            units_series.append(day_units)
            closed_series.append(day_closed)
            if day_orphan:
                orphan_markers.append({
                    'label_index': len(labels) - 1,
                    'orphan_count': day_orphan,
                })

        # Fix: RP / unidades del período completo (no solo hoy).
        range_rp = self._kc_range_rp_stats(
            lines, date_from, date_to, work_center_id=work_center_id)

        for line in lines:
            cmp_today = self._kc_day_daily_cmp(line, today)
            blocking = Consumption._kc_find_blocking_daily_cmp(
                line, today, company=line.company_id)
            if blocking:
                lines_blocked_count += 1
            if cmp_today and cmp_today.state == 'done':
                lines_closed_today += 1

            last_done = Consumption.search([
                ('consumption_mode', '=', 'daily'),
                ('production_line_id', '=', line.id),
                ('state', '=', 'done'),
            ], order='consumption_date desc', limit=1)

            rp_t = self._kc_day_rp_stats(
                line, today, work_center_id=work_center_id)

            orphan_line = 0
            for day in self._kc_iter_dates(date_from, date_to):
                status, _cmp = self._kc_cell_status(
                    line, day, work_center_id=work_center_id)
                if status == 'orphan':
                    orphan_line += 1

            op_code, op_label = self._kc_operational_status(
                line, today, cmp_today, blocking, orphan_line > 0)

            action_type = False
            action_label = False
            action_res_id = False
            action_date = False
            if op_code == 'ok' and cmp_today:
                action_type = 'view_cmp'
                action_label = _('Ver consumo')
                action_res_id = cmp_today.id
            elif op_code == 'open' and cmp_today:
                action_type = 'open_cmp'
                action_label = _('Validar')
                action_res_id = cmp_today.id
            elif op_code == 'blocked' and blocking:
                action_type = 'open_cmp'
                action_label = _('Ir %(date)s', date=fields.Date.to_string(blocking.consumption_date))
                action_res_id = blocking.id
            elif op_code == 'orphan':
                target_day = today
                for day in reversed(list(self._kc_iter_dates(date_from, d_to))):
                    status, _c = self._kc_cell_status(
                        line, day, work_center_id=work_center_id)
                    if status == 'orphan':
                        target_day = day
                        break
                action_type = 'create_cmp'
                action_label = _('Crear consumo')
                action_date = fields.Date.to_string(target_day)

            state_labels = dict(
                Consumption._fields['state']._description_selection(self.env))
            cmp_state_label = (
                state_labels.get(cmp_today.state) if cmp_today else False)

            line_status.append({
                'line_id': line.id,
                'line_name': line.name,
                'line_code': line.code or '',
                'last_cmp_validated_date': fields.Date.to_string(
                    last_done.consumption_date) if last_done else False,
                'cmp_today_id': cmp_today.id if cmp_today else False,
                'cmp_today_name': cmp_today.display_name if cmp_today else False,
                'cmp_today_state': cmp_today.state if cmp_today else False,
                'cmp_today_state_label': cmp_state_label,
                'operational_status': op_code,
                'operational_status_label': op_label,
                'rp_count_today': rp_t['rp_count'],
                'units_today': rp_t['units'],
                'is_blocked': bool(blocking),
                'blocking_cmp_id': blocking.id if blocking else False,
                'orphan_days_in_range': orphan_line,
                'action_type': action_type,
                'action_label': action_label,
                'action_res_id': action_res_id,
                'action_date': action_date,
            })

        lines_total = len(lines)
        compliance_percent = None
        if show_calendar and lines_total:
            possible = 0
            closed = 0
            for line in lines:
                for day in self._kc_iter_dates(date_from, date_to):
                    rp = self._kc_day_rp_stats(
                        line, day, work_center_id=work_center_id)
                    if not rp['rp_count']:
                        continue
                    possible += 1
                    cmp = self._kc_day_daily_cmp(line, day)
                    if cmp and cmp.state == 'done':
                        closed += 1
            compliance_percent = round(100.0 * closed / possible, 1) if possible else None

        alerts = (
            self._kc_build_alerts(lines, today, work_center_id=work_center_id)
            if d_to >= today >= d_from else []
        )

        return {
            'kpis': {
                'lines_closed': lines_closed_today,
                'lines_total': lines_total,
                'lines_closed_status': self._kc_status_color(
                    lines_total - lines_closed_today, 0, 1),
                'cmp_open_count': len(open_cmps),
                'cmp_open_status': self._kc_status_color(len(open_cmps), 0, 2),
                'lines_blocked_count': lines_blocked_count,
                'lines_blocked_status': self._kc_status_color(
                    lines_blocked_count, 0, 0),
                'rp_count': range_rp['rp_count'],
                'units_produced': range_rp['units'],
                'rp_queue_count': rp_queue,
                'rp_queue_status': self._kc_status_color(rp_queue, 0, 3),
                'orphan_days_count': orphan_days_count,
                'orphan_days_status': self._kc_status_color(
                    orphan_days_count, 0, 2),
                'compliance_percent': compliance_percent,
            },
            'alerts': alerts,
            'line_status': line_status,
            'compliance_calendar': self._kc_build_calendar(
                lines, date_from, date_to, work_center_id=work_center_id)
            if show_calendar else None,
            'chart_data': {
                'labels': labels,
                'units_produced': units_series,
                'lines_closed': closed_series,
                'lines_total': lines_total,
                'orphan_markers': orphan_markers,
            },
        }

    @api.model
    def _kc_build_planning(self, lines, date_from, date_to, work_center_id=False):
        Plan = self.env['kc.production.plan.line']
        Center = self.env['kc.work.center']
        domain = self._kc_plan_domain(lines, date_from, date_to, work_center_id)
        plans = Plan.search(domain)

        active = plans.filtered(lambda p: p.state in ('draft', 'confirmed', 'in_progress'))
        delayed = plans.filtered(lambda p: p.is_delayed)
        overloaded = plans.filtered(lambda p: p.is_overloaded)

        centers = Center.search([
            ('production_line_id', 'in', lines.ids or [0]),
            ('active', '=', True),
        ], order='sequence, name')
        if work_center_id:
            centers = centers.filtered(lambda c: c.id == work_center_id)

        centers_active = len(centers.filtered(lambda c: c.state == 'active'))
        centers_maint = len(centers.filtered(lambda c: c.state == 'maintenance'))

        # Ocupación: horas planificadas vs capacidad del período.
        days = max((fields.Date.from_string(date_to)
                    - fields.Date.from_string(date_from)).days + 1, 1)
        occupancy = []
        range_from_dt = fields.Datetime.from_string(
            self._get_datetime_bounds(date_from, date_to)[0])
        range_to_dt = fields.Datetime.from_string(
            self._get_datetime_bounds(date_from, date_to)[1])
        for center in centers:
            capacity = (center.capacity_qty or 1.0) * (
                (center.efficiency_pct or 100.0) / 100.0)
            # Capacidad del período ≈ capacidad diaria × días (misma base que sobrecarga).
            capacity_period = capacity * days
            planned_h = 0.0
            c_plans = plans.filtered(
                lambda p, cid=center.id: p.work_center_id.id == cid
                and p.state != 'cancelled')
            for plan in c_plans:
                start = max(plan.date_planned_start, range_from_dt)
                end = min(plan.date_planned_end, range_to_dt)
                if end > start:
                    planned_h += (end - start).total_seconds() / 3600.0
            pct = round(100.0 * planned_h / capacity_period, 1) if capacity_period else 0.0
            occupancy.append({
                'center_id': center.id,
                'center_name': center.display_name or center.name,
                'line_name': center.production_line_id.name,
                'state': center.state,
                'planned_hours': round(planned_h, 1),
                'capacity_hours': round(capacity_period, 1),
                'occupancy_pct': pct,
                'is_over': pct > 100.0,
            })

        delayed_list = []
        for plan in delayed.sorted('date_planned_end')[:8]:
            delayed_list.append({
                'plan_id': plan.id,
                'name': plan.display_name or plan.name,
                'sale_order': plan.sale_order_id.name if plan.sale_order_id else '',
                'product': plan.product_id.display_name,
                'technical_description': plan.technical_description or '',
                'center': plan.work_center_id.display_name,
                'date_end': fields.Datetime.to_string(plan.date_planned_end),
                'state': plan.state,
            })

        # Top backlog (excluye ya planificados vía search_fetch del modelo).
        backlog_top = []
        pending_qty_total = 0.0
        backlog_count = 0
        if 'kc.production.backlog' in self.env:
            Backlog = self.env['kc.production.backlog']
            bl_domain = [('production_line_id', 'in', lines.ids or [0])]
            backlogs = Backlog.search(bl_domain, limit=50)
            backlog_count = len(backlogs)
            pending_qty_total = sum(backlogs.mapped('pending_qty'))
            for bl in sorted(backlogs, key=lambda b: b.pending_qty or 0.0, reverse=True)[:5]:
                backlog_top.append({
                    'id': bl.id,
                    'sale_order': bl.sale_order_id.name,
                    'partner': bl.partner_id.name if bl.partner_id else '',
                    'product': bl.product_id.display_name,
                    'technical_description': bl.technical_description or '',
                    'pending_qty': bl.pending_qty,
                    'status': bl.status,
                })

        return {
            'kpis': {
                'plans_active': len(active),
                'plans_delayed': len(delayed),
                'plans_delayed_status': self._kc_status_color(len(delayed), 0, 2),
                'plans_overloaded': len(overloaded),
                'plans_overloaded_status': self._kc_status_color(len(overloaded), 0, 1),
                'centers_active': centers_active,
                'centers_maintenance': centers_maint,
                'centers_maint_status': self._kc_status_color(centers_maint, 0, 0),
                'backlog_count': backlog_count,
                'backlog_pending_qty': pending_qty_total,
            },
            'occupancy': occupancy,
            'delayed': delayed_list,
            'backlog_top': backlog_top,
        }

    @api.model
    def _kc_build_compliance(self, lines, date_from, date_to, work_center_id=False):
        Plan = self.env['kc.production.plan.line']
        domain = self._kc_plan_domain(lines, date_from, date_to, work_center_id)
        plans = Plan.search(domain)

        planned_qty = sum(plans.mapped('planned_qty'))
        produced_qty = sum(plans.mapped('qty_produced'))
        variance = sum(plans.mapped('variance'))
        pct = None
        if float_compare(planned_qty, 0.0, precision_digits=4) > 0:
            pct = round(100.0 * produced_qty / planned_qty, 1)

        # Serie planificado vs real por centro (o por día si un solo centro / pocos).
        by_center = {}
        for plan in plans:
            key = plan.work_center_id.id or 0
            name = plan.work_center_id.display_name if plan.work_center_id else _('Sin centro')
            bucket = by_center.setdefault(key, {
                'label': name,
                'planned': 0.0,
                'produced': 0.0,
            })
            bucket['planned'] += plan.planned_qty or 0.0
            bucket['produced'] += plan.qty_produced or 0.0

        labels = []
        planned_series = []
        produced_series = []
        for bucket in sorted(by_center.values(), key=lambda b: b['label']):
            labels.append(bucket['label'])
            planned_series.append(round(bucket['planned'], 2))
            produced_series.append(round(bucket['produced'], 2))

        status = 'teal'
        if pct is None:
            status = 'teal'
        elif pct >= 95:
            status = 'green'
        elif pct >= 70:
            status = 'amber'
        else:
            status = 'red'

        variance_status = 'green' if variance >= 0 else 'red'

        return {
            'kpis': {
                'compliance_pct': pct,
                'compliance_status': status,
                'planned_qty': planned_qty,
                'produced_qty': produced_qty,
                'variance': variance,
                'variance_status': variance_status,
                'plans_count': len(plans),
            },
            'chart_data': {
                'labels': labels,
                'planned': planned_series,
                'produced': produced_series,
            },
        }

    @api.model
    def _kc_build_calendar(self, lines, date_from, date_to, work_center_id=False):
        dates = [fields.Date.to_string(d) for d in self._kc_iter_dates(date_from, date_to)]
        date_labels = [
            fields.Date.from_string(d).strftime('%d') for d in dates]
        rows = []
        for line in lines:
            cells = []
            for d_str in dates:
                day = fields.Date.from_string(d_str)
                status, cmp = self._kc_cell_status(
                    line, day, work_center_id=work_center_id)
                cells.append({
                    'date': d_str,
                    'status': status,
                    'cmp_id': cmp.id if cmp else False,
                })
            rows.append({
                'line_id': line.id,
                'line_name': line.name,
                'cells': cells,
            })
        return {
            'date_labels': date_labels,
            'dates': dates,
            'rows': rows,
        }
