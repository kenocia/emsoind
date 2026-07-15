# -*- coding: utf-8 -*-

import hmac
import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.addons.web.controllers.utils import clean_action

_logger = logging.getLogger(__name__)

# Bloqueo temporal anti fuerza bruta: tras N fallos en la ventana, se rechaza.
MAX_FAILED_ATTEMPTS = 5
ATTEMPT_WINDOW_MINUTES = 10


class KcPinAuthorization(models.TransientModel):
    """Servicio + contenedor del diálogo de autorización por PIN.

    Es un TransientModel que cumple dos roles:
    - Hospeda la vista 'form' (target='new') que el helper del mixin abre. Esa
      vista solo monta el widget OWL 'kc_pin_pad'; sus campos guardan el destino
      de la autorización (modelo, ids, método a re-ejecutar y motivo).
    - Expone los métodos @api.model que el widget invoca vía ORM:
      `get_authorizer_employees` y `verify_pin`.
    """
    _name = 'kc.pin.authorization'
    _description = 'Autorización por PIN'

    res_model = fields.Char(string='Modelo destino', required=True)
    res_ids = fields.Char(string='IDs destino (JSON)', required=True)
    callback_method = fields.Char(string='Método a ejecutar', required=True)
    reason = fields.Char(string='Motivo')
    # Campo de apoyo: solo existe para anclar el widget OWL del teclado.
    pin = fields.Char(string='PIN')

    @api.model
    def get_authorizer_employees(self):
        """Empleados que pueden autorizar (los que tienen PIN configurado).

        Se ejecuta con sudo porque el campo `pin` de hr.employee está
        restringido; solo se exponen id y nombre, nunca el PIN.
        """
        return self.env['hr.employee'].sudo().search_read(
            [('pin', '!=', False)], ['id', 'name'], order='name',
        )

    @api.model
    def kc_pin_dialog_data(self):
        """Datos que el diálogo necesita para decidir su modo (estilo PdV).

        Si el usuario actual tiene un empleado con PIN configurado, el diálogo
        pide directamente SU PIN (modo 'self'); si no, muestra el buscador de
        empleados (modo 'select'). En ambos casos se devuelve la lista de
        empleados con PIN por si se quiere autorizar con otro (un supervisor).
        """
        employee = self.env.user.employee_id
        current = False
        if employee:
            current = {
                'id': employee.id,
                'name': employee.name,
                'has_pin': bool(employee.sudo().pin),
            }
        return {
            'current_employee': current,
            'employees': self.get_authorizer_employees(),
        }

    @api.model
    def verify_pin(self, employee_id, pin, res_model=None, res_ids=None,
                   reason=None):
        """Valida el PIN del empleado y, si es correcto, registra la
        autorización en el/los registros destino.

        Devuelve un dict {success, error?, employee_id?, employee_name?} para
        que el widget muestre el feedback en línea sin recargar.
        """
        employee = self.env['hr.employee'].sudo().browse(int(employee_id))
        if not employee.exists():
            return {'success': False, 'error': _('Empleado no válido.')}

        if self._is_employee_locked(employee):
            return {'success': False, 'error': _(
                'Demasiados intentos fallidos. Espere unos minutos e intente '
                'de nuevo.'
            )}

        stored_pin = employee.pin or ''
        # Comparación de tiempo constante para no filtrar el PIN por timing.
        is_valid = bool(stored_pin) and hmac.compare_digest(
            str(stored_pin), str(pin or '')
        )

        self._log_attempt(employee, res_model, res_ids, reason, is_valid)

        if not is_valid:
            return {'success': False, 'error': _('PIN incorrecto.')}

        if res_model and res_ids and res_model in self.env:
            records = self.env[res_model].browse(json.loads(res_ids)).exists()
            if records and hasattr(records, '_kc_pin_register_authorization'):
                records._kc_pin_register_authorization(employee, reason)

        return {
            'success': True,
            'employee_id': employee.id,
            'employee_name': employee.name,
        }

    @api.model
    def kc_pin_run_callback(self, res_model, res_ids, callback_method,
                            employee_id):
        """Re-ejecuta el método de negocio autorizado y devuelve la acción ya
        normalizada.

        El widget no puede invocar el método de negocio con un `orm.call`
        directo y pasar el resultado a `doAction`, porque las acciones que
        devuelven los botones (p. ej. un `ir.actions.act_window` construido al
        vuelo) no incluyen la clave `views` que el cliente web espera; esa
        normalización solo ocurre en el controlador `call_button`. Aquí
        replicamos ese paso con `clean_action` para evitar el error
        "Cannot read properties of undefined (reading 'map')".
        """
        if not res_model or res_model not in self.env:
            return False
        records = self.env[res_model].browse(json.loads(res_ids or '[]')).exists()
        method = getattr(records.with_context(
            kc_pin_authorized=True,
            kc_pin_employee_id=employee_id,
        ), callback_method)
        result = method()
        if isinstance(result, dict) and result.get('type'):
            return clean_action(result, self.env)
        return result

    @api.model
    def _is_employee_locked(self, employee):
        window_start = fields.Datetime.now() - timedelta(
            minutes=ATTEMPT_WINDOW_MINUTES)
        recent_fails = self.env['kc.pin.authorization.log'].sudo().search_count([
            ('employee_id', '=', employee.id),
            ('result', '=', 'fail'),
            ('authorization_date', '>=', window_start),
        ])
        return recent_fails >= MAX_FAILED_ATTEMPTS

    @api.model
    def _log_attempt(self, employee, res_model, res_ids, reason, success):
        res_id = False
        if res_ids:
            try:
                ids = json.loads(res_ids)
                res_id = ids[0] if ids else False
            except (ValueError, TypeError):
                res_id = False
        self.env['kc.pin.authorization.log'].sudo().create({
            'employee_id': employee.id,
            'user_id': self.env.user.id,
            'res_model': res_model or False,
            'res_id': res_id,
            'reason': reason or False,
            'result': 'success' if success else 'fail',
        })
