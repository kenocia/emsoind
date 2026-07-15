# -*- coding: utf-8 -*-

import json

from markupsafe import Markup, escape

from odoo import _, fields, models
from odoo.tools import format_datetime
from odoo.tools.safe_eval import safe_eval


class KcPinAuthorizationMixin(models.AbstractModel):
    """Mixin que da a cualquier modelo la capacidad de exigir autorización por
    PIN y dejar rastro de quién autorizó.

    Uso típico en un modelo de negocio::

        class SaleOrder(models.Model):
            _name = 'sale.order'
            _inherit = ['sale.order', 'kc.pin.authorization.mixin']

            def action_confirm(self):
                if not self.env.context.get('kc_pin_authorized'):
                    return self.kc_action_require_pin(
                        'action_confirm', reason=_('Confirmación de pedido'))
                return super().action_confirm()

    Requiere que el modelo herede también `mail.thread` para el registro en el
    chatter (si no lo hereda, el rastro queda en los campos y en el log central).
    """
    _name = 'kc.pin.authorization.mixin'
    _description = 'Mixin de Autorización por PIN'

    kc_pin_authorized_employee_id = fields.Many2one(
        'hr.employee', string='Autorizado por (PIN)', readonly=True,
        copy=False, ondelete='set null',
    )
    kc_pin_authorization_date = fields.Datetime(
        string='Fecha de autorización', readonly=True, copy=False,
    )
    kc_pin_authorized_user_id = fields.Many2one(
        'res.users', string='Autorizado en sesión de', readonly=True,
        copy=False, ondelete='set null',
    )

    def _kc_pin_guard(self, operation, callback_method):
        """Punto de enganche configurable para los módulos.

        Llamar al inicio del método objetivo. Si existe una regla activa para
        (este modelo, `operation`) cuyo dominio aplica a estos registros, y aún
        no se ha autorizado en este flujo, devuelve la acción del diálogo de PIN
        (que al validar re-ejecuta `callback_method`). Si no aplica, devuelve
        False y el método continúa normalmente.

        Uso típico::

            def button_validate(self):
                action = self._kc_pin_guard('validate', 'button_validate')
                if action:
                    return action
                return super().button_validate()
        """
        if self.env.context.get('kc_pin_authorized'):
            return False
        rules = self.env['kc.pin.authorization.rule']._rules_for(
            self._name, operation)
        if not rules:
            return False
        matching = rules.filtered(lambda r: self._kc_match_domain(r.domain))
        if not matching:
            return False
        return self.kc_action_require_pin(
            callback_method, reason=matching[0].reason)

    def _kc_match_domain(self, domain_str):
        """True si la regla aplica: dominio vacío (siempre) o al menos un
        registro de self cumple el dominio."""
        if not domain_str or not domain_str.strip() or domain_str.strip() == '[]':
            return True
        domain = safe_eval(domain_str)
        if not domain:
            return True
        return bool(self.filtered_domain(domain))

    def kc_action_require_pin(self, callback_method, reason=None):
        """Devuelve la acción que abre el diálogo de PIN (modal que bloquea el
        fondo). Tras validar, el diálogo re-ejecuta `callback_method` sobre estos
        mismos registros con el contexto `kc_pin_authorized=True`.
        """
        return {
            'type': 'ir.actions.act_window',
            'name': _('Autorización requerida'),
            'res_model': 'kc.pin.authorization',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_res_model': self._name,
                'default_res_ids': json.dumps(self.ids),
                'default_callback_method': callback_method,
                'default_reason': reason or _('Autorización requerida'),
            },
        }

    def _kc_format_pin_reason_html(self, reason):
        """Convierte el motivo en texto plano a HTML legible en el chatter."""
        lines = [line.strip() for line in (reason or '').splitlines() if line.strip()]
        if not lines:
            return Markup('')

        intro = escape(lines[0])
        items = [escape(line[2:]) for line in lines[1:] if line.startswith('- ')]
        extra = [
            escape(line) for line in lines[1:]
            if not line.startswith('- ')
        ]

        parts = [Markup('<p>%s</p>') % intro]
        if items:
            parts.append(Markup(
                '<ul>%s</ul>'
            ) % Markup('').join(Markup('<li>%s</li>') % item for item in items))
        for line in extra:
            parts.append(Markup('<p>%s</p>') % line)
        return Markup('').join(parts)

    def _kc_pin_register_authorization(self, employee, reason=None):
        """Graba el rastro de la autorización: campos del registro + chatter.

        El log central lo crea el servicio `verify_pin`; aquí solo se persisten
        los campos visibles y el mensaje en el hilo del documento.
        """
        now = fields.Datetime.now()
        self.write({
            'kc_pin_authorized_employee_id': employee.id,
            'kc_pin_authorization_date': now,
            'kc_pin_authorized_user_id': self.env.user.id,
        })
        for record in self:
            if hasattr(record, 'message_post'):
                body = Markup(
                    '<p>%(intro)s <strong>%(employee)s</strong> %(on)s %(date)s.</p>'
                ) % {
                    'intro': _('Autorizado por'),
                    'employee': escape(employee.name),
                    'on': _('el'),
                    'date': escape(format_datetime(self.env, now)),
                }
                reason_html = record._kc_format_pin_reason_html(reason)
                if reason_html:
                    body = Markup('%s%s') % (body, reason_html)
                record.message_post(body=body)
