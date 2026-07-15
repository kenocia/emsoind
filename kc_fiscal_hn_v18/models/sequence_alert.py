# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta


class SequenceAlert(models.Model):
    _name = 'kc_fiscal_hn.sequence.alert'
    _description = 'Alertas de Secuencias Fiscales'
    _order = 'create_date desc'

    sequence_id = fields.Many2one('ir.sequence', string='Secuencia', required=True, ondelete='cascade')
    alert_type = fields.Selection([
        ('warning', 'Advertencia'),
        ('critical', 'Crítico'),
        ('expired', 'Expirado')
    ], string='Tipo de Alerta', required=True)
    
    message = fields.Text(string='Mensaje', required=True)
    usage_percentage = fields.Float(string='Porcentaje Usado (%)', digits=(5, 2))
    current_number = fields.Integer(string='Número Actual')
    range_start = fields.Integer(string='Inicio de Rango')
    range_end = fields.Integer(string='Fin de Rango')
    
    # Estado de la alerta
    state = fields.Selection([
        ('active', 'Activa'),
        ('acknowledged', 'Reconocida'),
        ('resolved', 'Resuelta'),
        ('expired', 'Expirada')
    ], string='Estado', default='active')
    
    acknowledged_by = fields.Many2one('res.users', string='Reconocida por')
    acknowledged_date = fields.Datetime(string='Fecha de Reconocimiento')
    resolved_by = fields.Many2one('res.users', string='Resuelta por')
    resolved_date = fields.Datetime(string='Fecha de Resolución')
    resolution_notes = fields.Text(string='Notas de Resolución')
    
    # Campos de seguimiento
    create_date = fields.Datetime(string='Fecha de Creación', default=fields.Datetime.now)
    company_id = fields.Many2one('res.company', string='Compañía', 
                                default=lambda self: self.env.company)
    
    @api.model_create_multi
    def create(self, vals_list):
        """Crear alertas con validaciones"""
        alerts = []
        for vals in vals_list:
            # Verificar si ya existe una alerta activa para esta secuencia
            existing_alert = self.search([
                ('sequence_id', '=', vals.get('sequence_id')),
                ('alert_type', '=', vals.get('alert_type')),
                ('state', '=', 'active')
            ], limit=1)
            
            if existing_alert:
                # Actualizar alerta existente
                existing_alert.write({
                    'message': vals.get('message'),
                    'usage_percentage': vals.get('usage_percentage'),
                    'current_number': vals.get('current_number'),
                    'range_start': vals.get('range_start'),
                    'range_end': vals.get('range_end'),
                    'create_date': fields.Datetime.now()
                })
                alerts.append(existing_alert)
            else:
                # Crear nueva alerta
                new_alert = super().create([vals])
                alerts.extend(new_alert)
        
        return alerts
    
    def action_acknowledge(self):
        """Reconocer alerta"""
        self.ensure_one()
        self.write({
            'state': 'acknowledged',
            'acknowledged_by': self.env.user.id,
            'acknowledged_date': fields.Datetime.now()
        })
    
    def action_resolve(self):
        """Resolver alerta"""
        self.ensure_one()
        return {
            'name': _('Resolver Alerta'),
            'type': 'ir.actions.act_window',
            'res_model': 'kc_fiscal_hn.wizard.resolve_alert',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_alert_id': self.id,
                'default_sequence_id': self.sequence_id.id,
                'default_alert_type': self.alert_type
            }
        }
    
    def action_view_sequence(self):
        """Ver secuencia relacionada"""
        self.ensure_one()
        return {
            'name': _('Secuencia Fiscal'),
            'type': 'ir.actions.act_window',
            'res_model': 'ir.sequence',
            'res_id': self.sequence_id.id,
            'view_mode': 'form',
            'target': 'current'
        }
    
    def action_view_usage(self):
        """Ver uso de la secuencia"""
        self.ensure_one()
        return self.sequence_id.action_view_fiscal_usage()
    
    @api.model
    def cleanup_expired_alerts(self):
        """Limpiar alertas expiradas (más de 30 días)"""
        cutoff_date = fields.Datetime.now() - timedelta(days=30)
        expired_alerts = self.search([
            ('create_date', '<', cutoff_date),
            ('state', 'in', ['acknowledged', 'resolved'])
        ])
        
        if expired_alerts:
            expired_alerts.write({'state': 'expired'})
        
        return len(expired_alerts)
    
    @api.model
    def get_active_alerts_count(self):
        """Obtener cantidad de alertas activas"""
        return self.search_count([('state', '=', 'active')])
    
    @api.model
    def get_alerts_by_type(self):
        """Obtener alertas agrupadas por tipo"""
        alerts = self.search([('state', '=', 'active')])
        
        result = {
            'warning': 0,
            'critical': 0,
            'expired': 0
        }
        
        for alert in alerts:
            result[alert.alert_type] += 1
        
        return result
    
    @api.depends('sequence_id', 'sequence_id.name', 'alert_type')
    def _compute_display_name(self) -> None:
        """Nombre personalizado para las alertas."""
        type_labels = dict(self._fields['alert_type'].selection)
        for alert in self:
            seq_name = alert.sequence_id.name or _('Sin secuencia')
            alert_type = alert.alert_type or ''
            if isinstance(alert_type, str) and alert_type:
                type_label = type_labels.get(
                    alert_type, alert_type,
                ).upper()
            else:
                type_label = _('SIN TIPO')
            alert.display_name = f'{seq_name} - {type_label}' 