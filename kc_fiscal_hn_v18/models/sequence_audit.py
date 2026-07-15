# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class SequenceAudit(models.Model):
    _name = 'kc_fiscal_hn.sequence.audit'
    _description = 'Auditoría de Secuencias Fiscales'
    _order = 'create_date desc'

    sequence_id = fields.Many2one('ir.sequence', string='Secuencia', required=True, ondelete='cascade')
    action = fields.Selection([
        ('reset', 'Reinicio'),
        ('modify', 'Modificación'),
        ('create', 'Creación'),
        ('delete', 'Eliminación')
    ], string='Acción', required=True)
    
    old_number = fields.Integer(string='Número Anterior')
    new_number = fields.Integer(string='Número Nuevo')
    reason = fields.Text(string='Motivo')
    
    user_id = fields.Many2one('res.users', string='Usuario', required=True, default=lambda self: self.env.user)
    create_date = fields.Datetime(
        string='Fecha',
        default=lambda self: fields.Datetime.now(),
        help='Fecha y hora en zona horaria Honduras (UTC-6)',
    )
    company_id = fields.Many2one('res.company', string='Compañía', 
                                default=lambda self: self.env.company)
    
    # Campos adicionales para contexto
    ip_address = fields.Char(string='Dirección IP')
    session_id = fields.Char(string='ID de Sesión')
    
    @api.depends('sequence_id', 'sequence_id.name', 'action', 'create_date')
    def _compute_display_name(self) -> None:
        """Nombre personalizado para registros de auditoría (zona Honduras)."""
        action_labels = dict(self._fields['action'].selection)
        for audit in self:
            ts = ''
            if audit.create_date:
                dt_hn = fields.Datetime.context_timestamp(
                    audit.with_context(tz='America/Tegucigalpa'),
                    audit.create_date,
                )
                ts = dt_hn.strftime('%Y-%m-%d %H:%M')
            seq_name = (
                audit.sequence_id.name
                if audit.sequence_id else _('Sin secuencia')
            )
            action_str = audit.action or ''
            if isinstance(action_str, str) and action_str:
                action_upper = action_labels.get(
                    action_str, action_str,
                ).upper()
            else:
                action_upper = _('SIN ACCIÓN')
            audit.display_name = f'{seq_name} - {action_upper} - {ts}'
    
    @api.model_create_multi
    def create(self, vals_list):
        """Crear registro de auditoría con información adicional y timestamp Honduras."""
        for vals in vals_list:
            if not vals.get('ip_address'):
                vals['ip_address'] = self.env.context.get('ip_address', 'N/A')
            if not vals.get('session_id'):
                vals['session_id'] = self.env.context.get('session_id', 'N/A')
            if not vals.get('create_date'):
                vals['create_date'] = fields.Datetime.now()
        return super().create(vals_list)
    
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
    
    @api.model
    def get_audit_summary(self, days=30):
        """Obtener resumen de auditoría de los últimos días"""
        from datetime import datetime, timedelta
        
        start_date = fields.Datetime.now() - timedelta(days=days)
        
        audits = self.search([
            ('create_date', '>=', start_date)
        ])
        
        summary = {
            'total_actions': len(audits),
            'resets': len(audits.filtered(lambda a: a.action == 'reset')),
            'modifications': len(audits.filtered(lambda a: a.action == 'modify')),
            'creations': len(audits.filtered(lambda a: a.action == 'create')),
            'deletions': len(audits.filtered(lambda a: a.action == 'delete')),
            'by_user': {},
            'by_sequence': {}
        }
        
        # Agrupar por usuario
        for audit in audits:
            user_name = audit.user_id.name
            if user_name not in summary['by_user']:
                summary['by_user'][user_name] = 0
            summary['by_user'][user_name] += 1
        
        # Agrupar por secuencia
        for audit in audits:
            sequence_name = audit.sequence_id.name
            if sequence_name not in summary['by_sequence']:
                summary['by_sequence'][sequence_name] = 0
            summary['by_sequence'][sequence_name] += 1
        
        return summary 