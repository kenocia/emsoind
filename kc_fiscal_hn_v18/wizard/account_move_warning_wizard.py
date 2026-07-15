# -*- coding: utf-8 -*-

import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMoveWarningWizard(models.TransientModel):
    _name = 'account.move.warning.wizard'
    _description = 'Advertencia Fiscal al Validar Factura'

    warning_message = fields.Text(string="Mensaje de advertencia", readonly=True)
    move_id = fields.Many2one('account.move', string='Factura', readonly=True)
    warning_type = fields.Selection([
        ('date', 'Advertencia de Fecha'),
        ('numbers', 'Advertencia de Números'),
        ('exoneracion', 'Advertencia de Exoneración'),
        ('general', 'Advertencia General')
    ], string='Tipo de Advertencia', default='general')

    def _get_move_to_post(self):
        """Obtiene la factura a publicar desde el wizard o el contexto."""
        self.ensure_one()
        if self.move_id:
            return self.move_id
        active_id = self.env.context.get('active_id')
        if active_id:
            move = self.env['account.move'].browse(active_id)
            if move.exists():
                return move
        active_ids = self.env.context.get('active_ids') or []
        if active_ids:
            move = self.env['account.move'].browse(active_ids[0])
            if move.exists():
                return move
        return self.env['account.move']

    def action_continue(self):
        """Continuar con la validación de la factura: publicar y cerrar el wizard."""
        self.ensure_one()
        move = self._get_move_to_post()
        if not move:
            raise UserError(_(
                'No se encontró la factura a confirmar. '
                'Cierre el aviso e intente confirmar de nuevo.'
            ))
        _logger.info(
            'FISCAL DEBUG: wizard Continuar — publicando factura %s',
            move.id,
        )
        move.with_context(skip_fiscal_warning=True).action_post()
        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        """Cancelar la validación"""
        return {'type': 'ir.actions.act_window_close'}
    
    @api.model
    def create_warning(self, message, move_id, warning_type='general'):
        """Método de clase para crear advertencias"""
        return self.create({
            'warning_message': message,
            'move_id': move_id,
            'warning_type': warning_type
        })
