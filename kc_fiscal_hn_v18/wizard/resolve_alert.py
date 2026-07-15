# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResolveAlertWizard(models.TransientModel):
    _name = 'kc_fiscal_hn.wizard.resolve_alert'
    _description = 'Resolver Alerta de Secuencia'

    alert_id = fields.Many2one('kc_fiscal_hn.sequence.alert', string='Alerta', required=True, readonly=True)
    sequence_id = fields.Many2one('ir.sequence', string='Secuencia', readonly=True)
    alert_type = fields.Selection([
        ('warning', 'Advertencia'),
        ('critical', 'Crítico'),
        ('expired', 'Expirado')
    ], string='Tipo de Alerta', readonly=True)
    
    resolution_action = fields.Selection([
        ('extend_range', 'Extender Rango'),
        ('reset_sequence', 'Reiniciar Secuencia'),
        ('request_new_range', 'Solicitar Nuevo Rango'),
        ('other', 'Otra Acción')
    ], string='Acción de Resolución', required=True)
    
    resolution_notes = fields.Text(string='Notas de Resolución', required=True)
    follow_up_date = fields.Date(string='Fecha de Seguimiento')
    assign_to = fields.Many2one('res.users', string='Asignar a')
    
    @api.onchange('alert_id')
    def _onchange_alert_id(self):
        """Cargar datos de la alerta"""
        if self.alert_id:
            self.sequence_id = self.alert_id.sequence_id.id
            self.alert_type = self.alert_id.alert_type
    
    @api.constrains('resolution_notes')
    def _check_resolution_notes(self):
        """Validar que se especifiquen notas de resolución"""
        for wizard in self:
            if wizard.resolution_notes and len(wizard.resolution_notes.strip()) < 10:
                raise ValidationError(_('Las notas de resolución deben tener al menos 10 caracteres'))
    
    def action_resolve_alert(self):
        """Resolver la alerta"""
        self.ensure_one()
        
        if not self.resolution_notes:
            raise ValidationError(_('Debe especificar las notas de resolución'))
        
        # Actualizar la alerta
        self.alert_id.write({
            'state': 'resolved',
            'resolved_by': self.env.user.id,
            'resolved_date': fields.Datetime.now(),
            'resolution_notes': self.resolution_notes
        })
        
        # Crear tarea de seguimiento si se especifica
        if self.follow_up_date or self.assign_to:
            self.env['kc_fiscal_hn.follow_up.task'].create({
                'alert_id': self.alert_id.id,
                'sequence_id': self.sequence_id.id,
                'action': self.resolution_action,
                'notes': self.resolution_notes,
                'due_date': self.follow_up_date,
                'assigned_to': self.assign_to.id if self.assign_to else False,
                'created_by': self.env.user.id
            })
        
        # Ejecutar acción específica según el tipo de resolución
        if self.resolution_action == 'extend_range':
            return self._action_extend_range()
        elif self.resolution_action == 'reset_sequence':
            return self._action_reset_sequence()
        elif self.resolution_action == 'request_new_range':
            return self._action_request_new_range()
        else:
            return self._action_other()
    
    def _action_extend_range(self):
        """Acción para extender el rango"""
        return {
            'name': _('Extender Rango Fiscal'),
            'type': 'ir.actions.act_window',
            'res_model': 'kc_fiscal_hn.wizard.extend_range',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sequence_id': self.sequence_id.id,
                'default_current_range_end': self.sequence_id.fiscal_range_end,
                'default_resolution_notes': self.resolution_notes
            }
        }
    
    def _action_reset_sequence(self):
        """Acción para reiniciar secuencia"""
        return {
            'name': _('Reiniciar Secuencia Fiscal'),
            'type': 'ir.actions.act_window',
            'res_model': 'kc_fiscal_hn.wizard.reset_sequence',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sequence_id': self.sequence_id.id,
                'default_reset_reason': self.resolution_notes
            }
        }
    
    def _action_request_new_range(self):
        """Acción para solicitar nuevo rango"""
        # Crear solicitud de nuevo rango
        request = self.env['kc_fiscal_hn.range.request'].create({
            'sequence_id': self.sequence_id.id,
            'request_type': 'new_range',
            'reason': self.resolution_notes,
            'requested_by': self.env.user.id,
            'priority': 'high' if self.alert_type == 'critical' else 'medium'
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Solicitud Creada'),
                'message': _('Se ha creado una solicitud de nuevo rango para la secuencia %s.') % self.sequence_id.name,
                'type': 'success',
            }
        }
    
    def _action_other(self):
        """Otra acción"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Alerta Resuelta'),
                'message': _('La alerta ha sido marcada como resuelta.'),
                'type': 'success',
            }
        } 