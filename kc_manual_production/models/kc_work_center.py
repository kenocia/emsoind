# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class KcWorkCenter(models.Model):
    """Centro de Trabajo: recurso operativo bajo una línea de producción."""
    _name = 'kc.work.center'
    _description = 'Centro de Trabajo'
    _order = 'production_line_id, sequence, name'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código')
    production_line_id = fields.Many2one(
        comodel_name='kc.production.line',
        string='Línea de Producción',
        required=True,
        ondelete='restrict',
        index=True,
    )
    company_id = fields.Many2one(
        related='production_line_id.company_id',
        store=True,
        readonly=True,
    )
    resource_calendar_id = fields.Many2one(
        comodel_name='resource.calendar',
        string='Horario / Turnos',
        help='Calendario de recursos usado para estimar capacidad disponible.',
    )
    capacity_qty = fields.Float(
        string='Capacidad',
        default=1.0,
        help='Capacidad nominal del centro en la unidad indicada.',
    )
    capacity_time_uom = fields.Selection(
        selection=[
            ('hour', 'Hora'),
            ('shift', 'Turno'),
            ('day', 'Día'),
        ],
        string='Unidad de capacidad',
        default='hour',
        required=True,
    )
    cost_hour = fields.Float(string='Costo por Hora')
    center_type = fields.Selection(
        selection=[
            ('machine', 'Máquina'),
            ('manual', 'Manual'),
            ('mixed', 'Mixto'),
        ],
        string='Tipo',
        default='manual',
        required=True,
    )
    efficiency_pct = fields.Float(
        string='Eficiencia (%)',
        default=100.0,
    )
    state = fields.Selection(
        selection=[
            ('active', 'Activo'),
            ('maintenance', 'Mantenimiento'),
            ('inactive', 'Inactivo'),
        ],
        string='Estado',
        default='active',
        required=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            'kc_work_center_name_line_uniq',
            'unique(name, production_line_id)',
            'Ya existe un centro de trabajo con ese nombre en la línea.',
        ),
    ]

    @api.constrains('efficiency_pct')
    def _check_efficiency_pct(self):
        for rec in self:
            if rec.efficiency_pct <= 0:
                raise ValidationError(_(
                    'La eficiencia del centro "%s" debe ser mayor que cero.'
                ) % rec.display_name)

    @api.depends('name', 'production_line_id', 'production_line_id.name')
    def _compute_display_name(self):
        for rec in self:
            if rec.production_line_id:
                rec.display_name = '%s (%s)' % (
                    rec.name or '',
                    rec.production_line_id.name or '',
                )
            else:
                rec.display_name = rec.name or ''
