# -*- coding: utf-8 -*-

import re

from odoo import _
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal

PIN_REGEX = r'\d{4,}'


class KcPinPortal(CustomerPortal):

    def _kc_user_employees(self):
        """Empleados vinculados al usuario actual (con sudo: el portal no tiene
        permiso de lectura sobre hr.employee)."""
        return request.env.user.sudo().employee_ids

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        # `kc_has_employee` es un flag de UI (no un contador). Este método
        # también lo invoca la ruta JSON `/my/counters`, cuya respuesta consume
        # el widget JS `PortalHomeCounters`: este recorre TODAS las claves
        # devueltas y hace `querySelector("[data-placeholder_count='<clave>']")`
        # para escribir su `.textContent`. Como no existe un elemento para
        # `kc_has_employee`, devolverlo ahí provoca "Cannot set properties of
        # null (setting 'textContent')". Por eso solo lo añadimos al renderizar
        # la página, no en la llamada de contadores.
        if request.httprequest.path != '/my/counters':
            values['kc_has_employee'] = bool(self._kc_user_employees())
        return values

    @route(['/my/pin'], type='http', auth='user', website=True)
    def kc_portal_change_pin(self, **post):
        employees = self._kc_user_employees()
        values = {
            'page_name': 'kc_pin',
            'has_employee': bool(employees),
        }

        if request.httprequest.method == 'POST' and employees:
            new_pin = (post.get('new_pin') or '').strip()
            confirm_pin = (post.get('confirm_pin') or '').strip()
            if not re.fullmatch(PIN_REGEX, new_pin):
                values['error'] = _(
                    'El PIN debe ser numérico y tener al menos 4 dígitos.')
            elif new_pin != confirm_pin:
                values['error'] = _('El PIN y su confirmación no coinciden.')
            else:
                # multi-compañía: mismo PIN en todos sus empleados.
                employees.write({'pin': new_pin})
                values['success'] = True

        return request.render(
            'kc_pin_authorization_portal.portal_my_pin', values)
