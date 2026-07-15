# -*- coding: utf-8 -*-

from odoo import api, fields, models


class KcPinAuthorizationLog(models.Model):
    """Auditoría central de autorizaciones por PIN.

    Registra TODOS los intentos (exitosos y fallidos) de cualquier módulo que
    use la funcionalidad. Se crea siempre con sudo() desde el servicio, por lo
    que los usuarios solo necesitan permiso de lectura.
    """
    _name = 'kc.pin.authorization.log'
    _description = 'Registro de Autorizaciones por PIN'
    _order = 'authorization_date desc, id desc'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one(
        'hr.employee', string='Empleado', required=True, ondelete='restrict',
        index=True,
    )
    user_id = fields.Many2one(
        'res.users', string='Usuario de sesión', required=True,
        ondelete='restrict',
    )
    authorization_date = fields.Datetime(
        string='Fecha y hora', default=fields.Datetime.now, required=True,
        index=True,
    )
    reason = fields.Char(string='Motivo')
    res_model = fields.Char(string='Modelo')
    res_id = fields.Integer(string='ID del registro')
    result = fields.Selection(
        selection=[
            ('success', 'Autorizado'),
            ('fail', 'PIN incorrecto'),
        ],
        string='Resultado', required=True, default='success', index=True,
    )
    document_ref = fields.Reference(
        selection='_selection_target_model', string='Documento',
        compute='_compute_document_ref',
    )

    @api.model
    def _selection_target_model(self):
        return [
            (model.model, model.name)
            for model in self.env['ir.model'].sudo().search([])
        ]

    @api.depends('res_model', 'res_id')
    def _compute_document_ref(self):
        for log in self:
            if log.res_model and log.res_id and log.res_model in self.env:
                log.document_ref = '%s,%s' % (log.res_model, log.res_id)
            else:
                log.document_ref = False
