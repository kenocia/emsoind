# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class ConsumidorFinalAudit(models.Model):
    _name = 'kc_fiscal_hn.consumidor.final.audit'
    _description = 'Auditoría de Bloqueos Consumidor Final'
    _order = 'create_date desc'

    partner_id = fields.Many2one('res.partner', string='Cliente')
    user_id = fields.Many2one(
        'res.users', string='Usuario',
        default=lambda self: self.env.user,
    )
    create_date = fields.Datetime(
        string='Fecha',
        default=lambda self: fields.Datetime.now(),
        help='Fecha y hora del intento bloqueado.',
    )
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id,
    )
    document_model = fields.Char(string='Modelo Documento')
    document_ref = fields.Char(string='Documento')
    monto = fields.Monetary(
        string='Monto Documento', currency_field='currency_id',
    )
    monto_maximo = fields.Monetary(
        string='Monto Máximo Permitido', currency_field='currency_id',
    )
    ip_address = fields.Char(string='Dirección IP')
    session_id = fields.Char(string='ID de Sesión')

    @api.depends('partner_id', 'document_ref', 'create_date')
    def _compute_display_name(self) -> None:
        for audit in self:
            ts = ''
            if audit.create_date:
                dt_hn = fields.Datetime.context_timestamp(
                    audit.with_context(tz='America/Tegucigalpa'),
                    audit.create_date,
                )
                ts = dt_hn.strftime('%Y-%m-%d %H:%M')
            doc = audit.document_ref or _('Documento nuevo')
            audit.display_name = f'{doc} - {ts}'

    @api.model
    def registrar_bloqueo(self, partner, document, monto, monto_maximo,
                          company):
        """Registra un intento bloqueado en una transacción independiente.

        Se usa un cursor separado y se hace commit para que el registro de
        auditoría persista aunque el UserError posterior haga rollback de la
        transacción principal.
        """
        vals = {
            'partner_id': partner.id if partner else False,
            'user_id': self.env.uid,
            'company_id': company.id,
            'currency_id': company.currency_id.id,
            'document_model': document._name if document else False,
            'document_ref': (
                document.display_name
                if document and document.id else _('Documento nuevo')
            ),
            'monto': monto,
            'monto_maximo': monto_maximo,
            'ip_address': self.env.context.get('ip_address', 'N/A'),
            'session_id': self.env.context.get('session_id', 'N/A'),
        }
        try:
            with self.env.registry.cursor() as new_cr:
                new_env = api.Environment(
                    new_cr, self.env.uid, self.env.context,
                )
                new_env[self._name].sudo().create(vals)
                new_cr.commit()
        except Exception:
            _logger.exception(
                'No se pudo registrar el bloqueo de Consumidor Final '
                'para el cliente %s', partner.id if partner else False,
            )
