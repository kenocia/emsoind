# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3
"""Extensión del lote de pagos para dispersión bancaria hondureña.

Fase 1: framework del exportador de archivo (TXT) por banco.
Fase 2: implementar el generador específico de cada banco (BAC, Atlántida,
        Ficohsa, Banpaís, Davivienda, ...).
"""

from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountBatchPayment(models.Model):
    _inherit = 'account.batch.payment'

    kenocia_bank_format = fields.Selection(
        selection=[
            ('bac', 'BAC Credomatic'),
            ('atlantida', 'Banco Atlántida'),
            ('ficohsa', 'Ficohsa'),
            ('banpais', 'Banpaís'),
            ('davivienda', 'Davivienda'),
        ],
        string='Formato de dispersión',
        help='Formato del archivo TXT que se entrega al banco para que '
             'genere las transferencias. Si se deja vacío, se usa el '
             'configurado en el diario.',
    )
    kenocia_source = fields.Selection(
        selection=[
            ('vendor', 'Proveedores'),
            ('payroll', 'Nómina'),
            ('manual', 'Manual'),
        ],
        string='Origen dispersión',
        default='manual',
        copy=False,
    )
    kenocia_file = fields.Binary(
        string='Archivo banco',
        readonly=True,
        copy=False,
    )
    kenocia_filename = fields.Char(
        string='Nombre archivo',
        readonly=True,
        copy=False,
    )
    kenocia_seq_id = fields.Many2one(
        comodel_name='kenocia.sequence',
        string='Secuencia dispersión',
        readonly=True,
        copy=False,
    )
    kenocia_sequence_name = fields.Char(
        string='Correlativo dispersión',
        readonly=True,
        copy=False,
        help='Correlativo Kenocia del depósito único al banco '
             '(1 dispersión = 1 correlativo).',
    )

    def _kenocia_assign_sequence(self, transaction_type):
        """Opción A: un correlativo Kenocia por LOTE (1 depósito = 1 número).

        Si el diario tiene una secuencia Kenocia activa para el tipo indicado,
        se consume UN correlativo y se guarda en el lote. Si no existe, se
        respeta la numeración nativa del lote sin bloquear la dispersión.
        """
        for batch in self:
            if batch.kenocia_sequence_name:
                continue
            sequence = self.env['kenocia.sequence'].search([
                ('journal_id', '=', batch.journal_id.id),
                ('transaction_type', '=', transaction_type),
                ('active', '=', True),
            ], limit=1)
            if not sequence:
                continue
            generated = sequence.generate_next()
            batch.write({
                'kenocia_seq_id': sequence.id,
                'kenocia_sequence_name': generated,
            })
        return True

    def _kenocia_effective_format(self):
        self.ensure_one()
        return self.kenocia_bank_format or self.journal_id.kenocia_bank_format

    def _kenocia_collect_file_lines(self):
        """Estructura de datos genérica que consumirá cada generador.

        Devuelve dict con encabezado (fecha, total, cantidad) y detalle por
        beneficiario (cuenta destino, monto, nombre, identificación, descripción).
        """
        self.ensure_one()
        lines = []
        for payment in self.payment_ids:
            partner = payment.partner_id
            bank = partner.bank_ids[:1]
            lines.append({
                'acc_number': bank.acc_number or '',
                'amount': payment.amount,
                'name': partner.display_name or '',
                'vat': partner.vat or '',
                'description': payment.memo or '',
            })
        return {
            'date': self.date,
            'total': sum(self.payment_ids.mapped('amount')),
            'count': len(self.payment_ids),
            'lines': lines,
        }

    def action_kenocia_generate_bank_file(self):
        self.ensure_one()
        bank_format = self._kenocia_effective_format()
        if not bank_format:
            raise UserError(_(
                'Configure el "Formato de dispersión" del banco en el lote '
                'o en el diario antes de generar el archivo.',
            ))
        generator = getattr(self, '_kenocia_render_%s' % bank_format, None)
        if not generator:
            # Fase 2: el generador del banco aún no está implementado.
            raise UserError(_(
                'El formato de archivo para %(bank)s todavía no está '
                'configurado (Fase 2). Comparta el layout/instructivo del '
                'banco para habilitarlo.',
                bank=dict(self._fields['kenocia_bank_format'].selection).get(
                    bank_format, bank_format,
                ),
            ))
        content, filename = generator(self._kenocia_collect_file_lines())
        self.write({
            'kenocia_file': content,
            'kenocia_filename': filename,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/account.batch.payment/%s/kenocia_file/%s?download=true' % (
                self.id, filename,
            ),
            'target': 'self',
        }
