# -*- coding: utf-8 -*-

from odoo import http, fields
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class FiscalController(http.Controller):

    @http.route('/fiscal/validate_sequence', type='json', auth='user', methods=['POST'])
    def validate_sequence(self, sequence_id, date=None):
        """ Valida una secuencia fiscal para una fecha específica """
        try:
            sequence = request.env['ir.sequence'].sudo().browse(sequence_id)
            
            if not sequence.exists():
                return {'success': False, 'error': 'Secuencia no encontrada.'}
            
            if not sequence.is_fiscal:
                return {'success': False, 'error': 'La secuencia no es fiscal.'}
            
            if not date:
                date = fields.Date.today()
            
            # Verificar si hay rango de fecha disponible
            if sequence.use_date_range:
                seq_date = request.env['ir.sequence.date_range'].sudo().search([
                    ('sequence_id', '=', sequence.id),
                    ('cai_validated', '=', True),
                    ('date_from', '<=', date),
                    ('date_to', '>=', date)
                ], limit=1)
                
                if not seq_date:
                    return {'success': False, 'error': 'No hay rango de fecha disponible.'}
                
                if not seq_date.cai:
                    return {'success': False, 'error': 'No hay CAI configurado para este rango.'}
                
                # Verificar si hay números disponibles
                if seq_date.number_next_actual > seq_date.rangoFinal:
                    return {'success': False, 'error': 'Rango de numeración agotado.'}
                
                return {
                    'success': True,
                    'cai': seq_date.cai,
                    'rango_inicial': seq_date.rangoInicial,
                    'rango_final': seq_date.rangoFinal,
                    'siguiente_numero': seq_date.number_next_actual,
                    'fecha_limite': seq_date.date_to.isoformat() if seq_date.date_to else '',
                    'can_continue': seq_date.number_next_actual <= seq_date.rangoFinal,
                }
            else:
                return {'success': True, 'message': 'Secuencia válida (sin rango de fecha)'}
                
        except Exception as e:
            _logger.error(f"❌ Error validando secuencia: {str(e)}")
            return {'success': False, 'error': str(e)}