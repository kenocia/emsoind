# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResetSequenceWizard(models.TransientModel):
    _name = 'kc_fiscal_hn.wizard.reset_sequence'
    _description = 'Reiniciar Secuencia Fiscal'

    sequence_id = fields.Many2one('ir.sequence', string='Secuencia', required=True, readonly=True)
    current_number = fields.Integer(string='Número Actual', readonly=True)
    fiscal_range_start = fields.Integer(string='Inicio de Rango', readonly=True)
    fiscal_range_end = fields.Integer(string='Fin de Rango', readonly=True)
    
    new_start_number = fields.Integer(string='Nuevo Número de Inicio', required=True)
    reset_reason = fields.Text(string='Motivo del Reinicio', required=True)
    confirm_reset = fields.Boolean(string='Confirmo el reinicio', default=False)
    
    @api.onchange('sequence_id')
    def _onchange_sequence_id(self):
        """Cargar datos de la secuencia"""
        if self.sequence_id:
            self.current_number = self.sequence_id.number_next_actual
            self.fiscal_range_start = self.sequence_id.fiscal_range_start
            self.fiscal_range_end = self.sequence_id.fiscal_range_end
            self.new_start_number = self.sequence_id.fiscal_range_start
    
    @api.constrains('new_start_number')
    def _check_new_start_number(self):
        """Validar el nuevo número de inicio"""
        for wizard in self:
            if wizard.sequence_id and wizard.new_start_number:
                if wizard.new_start_number < wizard.fiscal_range_start:
                    raise ValidationError(_('El nuevo número de inicio no puede ser menor al inicio del rango fiscal'))
                
                if wizard.new_start_number > wizard.fiscal_range_end:
                    raise ValidationError(_('El nuevo número de inicio no puede ser mayor al final del rango fiscal'))
    
    def action_reset_sequence(self):
        """Reiniciar la secuencia"""
        self.ensure_one()
        
        if not self.confirm_reset:
            raise ValidationError(_('Debe confirmar el reinicio de la secuencia'))
        
        if not self.reset_reason:
            raise ValidationError(_('Debe especificar el motivo del reinicio'))
        
        # Validar que el usuario tenga permisos
        if not self.env.user.has_group('account.group_account_manager'):
            raise ValidationError(_('Solo los administradores contables pueden reiniciar secuencias fiscales'))
        
        # Reiniciar la secuencia
        self.sequence_id.write({
            'number_next_actual': self.new_start_number
        })
        
        # Crear registro de auditoría
        self.env['kc_fiscal_hn.sequence.audit'].create({
            'sequence_id': self.sequence_id.id,
            'action': 'reset',
            'old_number': self.current_number,
            'new_number': self.new_start_number,
            'reason': self.reset_reason,
            'user_id': self.env.user.id
        })
        
        # Mostrar mensaje de confirmación
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Secuencia Reiniciada'),
                'message': _('La secuencia %s ha sido reiniciada exitosamente.') % self.sequence_id.name,
                'type': 'success',
            }
        } 