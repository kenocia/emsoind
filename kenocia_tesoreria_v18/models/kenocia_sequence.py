# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

import logging

from psycopg2 import OperationalError

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class KenociaSequence(models.Model):
    """Motor de correlativos bancarios con lock atómico SELECT FOR UPDATE NOWAIT."""

    _name = 'kenocia.sequence'
    _description = 'Secuencia Bancaria KENOCIA'
    _order = 'journal_id, transaction_type, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True,
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario',
        required=True,
        index=True,
        tracking=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    transaction_type = fields.Selection(
        selection=[
            ('cheque', 'Cheque'),
            ('deposito', 'Depósito'),
            ('debito', 'Débito'),
            ('credito', 'Crédito'),
            ('transferencia', 'Transferencia'),
            ('transferencia_banco', 'Transferencia Bancaria'),
            ('efectivo', 'Efectivo'),
        ],
        string='Tipo de transacción',
        required=True,
        index=True,
        tracking=True,
    )
    prefix = fields.Char(
        string='Prefijo',
        required=True,
        tracking=True,
        help='Prefijo concatenado al número. Ejemplo: CHQ/BCO/2026/',
    )
    next_number = fields.Integer(
        string='Próximo número',
        required=True,
        default=1,
        tracking=True,
    )
    padding = fields.Integer(
        string='Dígitos (padding)',
        required=True,
        default=4,
        tracking=True,
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
        tracking=True,
    )
    last_generated = fields.Char(
        string='Último número emitido',
        readonly=True,
        copy=False,
        tracking=True,
    )
    void_count = fields.Integer(
        string='Huecos por anulación',
        readonly=True,
        default=0,
        copy=False,
        tracking=True,
    )
    preview = fields.Char(
        string='Vista previa',
        compute='_compute_preview',
        help='Próximo número que se generará al validar un pago.',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        related='journal_id.company_id',
        store=True,
        index=True,
    )

    _sql_constraints = [
        (
            'unique_journal_type',
            'UNIQUE(journal_id, transaction_type)',
            'Ya existe una secuencia activa para este tipo en este diario.',
        ),
        (
            'positive_next_number',
            'CHECK(next_number > 0)',
            'El número siguiente debe ser mayor a cero.',
        ),
        (
            'valid_padding',
            'CHECK(padding BETWEEN 1 AND 12)',
            'El padding debe estar entre 1 y 12 dígitos.',
        ),
    ]

    @api.depends('prefix', 'next_number', 'padding')
    def _compute_preview(self):
        for sequence in self:
            if sequence.prefix and sequence.next_number and sequence.padding:
                sequence.preview = (
                    f'{sequence.prefix}'
                    f'{str(sequence.next_number).zfill(sequence.padding)}'
                )
            else:
                sequence.preview = False

    @api.depends('name', 'journal_id', 'transaction_type')
    def _compute_display_name(self):
        type_labels = dict(self._fields['transaction_type'].selection)
        for sequence in self:
            type_label = type_labels.get(sequence.transaction_type, '')
            journal_name = sequence.journal_id.display_name or ''
            sequence.display_name = ' / '.join(
                part for part in (sequence.name, journal_name, type_label) if part
            ) or sequence.name or _('Secuencia')

    def generate_next(self):
        """Genera el siguiente correlativo con lock atómico anti-duplicados."""
        self.ensure_one()
        if not self.active:
            raise UserError(_('La secuencia está inactiva.'))
        try:
            self.env.cr.execute(
                'SELECT id FROM kenocia_sequence WHERE id = %s FOR UPDATE NOWAIT',
                (self.id,),
            )
        except OperationalError:
            raise UserError(_(
                'Otro usuario está generando un número para esta secuencia. '
                'Intente de nuevo en unos segundos.'
            )) from None

        self.invalidate_recordset(['next_number', 'last_generated'])
        generated = (
            f'{self.prefix}{str(self.next_number).zfill(self.padding)}'
        )
        self.write({
            'next_number': self.next_number + 1,
            'last_generated': generated,
        })
        self.message_post(
            body=_(
                'Número generado: <b>%(number)s</b>. '
                'Próximo correlativo: <b>%(next)s</b>.',
                number=generated,
                next=self.preview or '',
            ),
            subtype_xmlid='mail.mt_note',
        )
        return generated

    def register_void(self, voided_number, reason=None):
        """Registra un hueco por anulación de cheque sin reutilizar el número."""
        self.ensure_one()
        self.write({'void_count': self.void_count + 1})
        body = _(
            'Número anulado: <b>%(number)s</b>. '
            'Huecos acumulados: <b>%(count)s</b>.',
            number=voided_number,
            count=self.void_count,
        )
        if reason:
            body += '<br/>' + _('Motivo: %(reason)s', reason=reason)
        self.message_post(body=body, subtype_xmlid='mail.mt_note')
        return True
