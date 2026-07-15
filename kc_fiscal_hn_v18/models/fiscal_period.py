# -*- coding: utf-8 -*-

from calendar import monthrange

from odoo import _
from odoo.exceptions import ValidationError


def month_bounds(date):
    """Primer y último día del mes calendario de *date*."""
    first = date.replace(day=1)
    last_day = monthrange(date.year, date.month)[1]
    last = date.replace(day=last_day)
    return first, last


def check_fiscal_period(date_from, date_to):
    """Valida período SAR: un solo mes calendario completo."""
    if not date_from or not date_to:
        return
    if date_from > date_to:
        raise ValidationError(_(
            'La fecha inicial no puede ser posterior a la final.',
        ))
    if (date_from.year, date_from.month) != (date_to.year, date_to.month):
        raise ValidationError(_(
            'Las declaraciones SAR deben corresponder a un único '
            'mes calendario.\n\n'
            'Período ingresado: %(desde)s — %(hasta)s',
            desde=date_from,
            hasta=date_to,
        ))
    expected_from, expected_to = month_bounds(date_from)
    if date_from != expected_from or date_to != expected_to:
        raise ValidationError(_(
            'El período debe cubrir el mes calendario completo.\n\n'
            'Use: %(desde)s — %(hasta)s',
            desde=expected_from,
            hasta=expected_to,
        ))


def action_notify_and_reload(record, title, message, msg_type='success'):
    """Notificación y recarga del formulario del libro."""
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'title': title,
            'message': message,
            'type': msg_type,
            'sticky': False,
            'next': {
                'type': 'ir.actions.act_window',
                'res_model': record._name,
                'res_id': record.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
            },
        },
    }


def action_notify_and_open_list(
    env,
    model,
    domain,
    title,
    message,
    list_name=None,
    msg_type='success',
):
    """Notificación y apertura de lista filtrada (retenciones/exoneraciones)."""
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'title': title,
            'message': message,
            'type': msg_type,
            'sticky': False,
            'next': {
                'type': 'ir.actions.act_window',
                'name': list_name or title,
                'res_model': model,
                'view_mode': 'list,form',
                'domain': domain,
                'target': 'current',
                'context': {
                    **env.context,
                    'create': False,
                    'delete': False,
                },
            },
        },
    }


def numero_factura_ventas(move):
    """Número fiscal válido en libro de ventas (excluye borrador «/»)."""
    name = (move.name or '').strip()
    if not name or name == '/':
        return False
    return name


def numero_factura_compras(move):
    """Número válido en libros de compras/retenciones."""
    num = (move.correlativo_proveedor or move.name or '').strip()
    if not num or num == '/':
        return False
    return num
