# -*- coding: utf-8 -*-

import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Política de PIN: solo numérico, mínimo 4 dígitos.
PIN_REGEX = r'\d{4,}'


class ResUsers(models.Model):
    _inherit = 'res.users'

    kc_pin_new = fields.Char(
        string='Nuevo PIN',
        compute='_compute_kc_pin_blank', inverse='_inverse_kc_pin_new',
        store=False,
        help='Escriba un PIN numérico de al menos 4 dígitos para cambiar el '
             'PIN de autorización de su empleado.',
    )
    kc_pin_confirm = fields.Char(
        string='Confirmar PIN',
        compute='_compute_kc_pin_blank', inverse='_inverse_kc_pin_noop',
        store=False,
    )
    kc_has_employee = fields.Boolean(
        compute='_compute_kc_has_employee',
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            'kc_pin_new', 'kc_pin_confirm', 'kc_has_employee',
        ]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['kc_pin_new', 'kc_pin_confirm']

    @api.depends_context('uid')
    def _compute_kc_pin_blank(self):
        # Nunca exponemos el PIN actual: los campos siempre se muestran vacíos.
        for user in self:
            user.kc_pin_new = False
            user.kc_pin_confirm = False

    @api.depends('employee_ids')
    def _compute_kc_has_employee(self):
        for user in self:
            user.kc_has_employee = bool(user.sudo().employee_ids)

    def _inverse_kc_pin_noop(self):
        # El campo de confirmación no escribe nada por sí mismo.
        return

    def _inverse_kc_pin_new(self):
        for user in self:
            new_pin = (user.kc_pin_new or '').strip()
            if not new_pin:
                continue
            # Solo el propio usuario puede cambiar su PIN (salvo RR. HH.).
            if user.id != self.env.uid and not self.env.user.has_group(
                    'hr.group_hr_user'):
                raise UserError(_('Solo puede cambiar su propio PIN.'))
            self._kc_validate_pin_policy(new_pin)
            confirm = (user.kc_pin_confirm or '').strip()
            if confirm != new_pin:
                raise UserError(_('El PIN y su confirmación no coinciden.'))
            employees = user.sudo().employee_ids
            if not employees:
                raise UserError(_(
                    'No tiene un empleado vinculado al que asignar el PIN.'))
            # multi-compañía: se aplica el mismo PIN a todos sus empleados.
            employees.write({'pin': new_pin})

    @api.model
    def _kc_validate_pin_policy(self, pin):
        if not re.fullmatch(PIN_REGEX, pin or ''):
            raise ValidationError(_(
                'El PIN debe ser numérico y tener al menos 4 dígitos.'))
