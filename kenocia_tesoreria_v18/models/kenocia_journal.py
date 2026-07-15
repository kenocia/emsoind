# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, api, fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    kenocia_sequence_ids = fields.One2many(
        comodel_name='kenocia.sequence',
        inverse_name='journal_id',
        string='Secuencias tesorería',
    )
    kenocia_sequence_count = fields.Integer(
        string='Secuencias',
        compute='_compute_kenocia_sequence_count',
    )
    kenocia_missing_payment_account = fields.Boolean(
        string='Falta cuenta outstanding en métodos de pago',
        compute='_compute_kenocia_missing_payment_account',
        help='Algún método de pago del diario no tiene cuenta de pagos pendientes '
             'configurada; los pagos pueden quedar sin asiento contable.',
    )
    kenocia_cheque_native_seq_coexist = fields.Boolean(
        string='Cheque Kenocia conviviendo con secuencia dedicada nativa',
        compute='_compute_kenocia_cheque_native_seq_coexist',
        help='El diario tiene activa la "Secuencia de pago dedicada" nativa y, '
             'además, una secuencia Kenocia de cheque. Los cheques se numerarán '
             'con el correlativo Kenocia, no con la serie PAY nativa.',
    )
    kenocia_bank_format = fields.Selection(
        selection=[
            ('bac', 'BAC Credomatic'),
            ('atlantida', 'Banco Atlántida'),
            ('ficohsa', 'Ficohsa'),
            ('banpais', 'Banpaís'),
            ('davivienda', 'Davivienda'),
        ],
        string='Formato dispersión banco',
        help='Formato de archivo TXT por defecto para dispersiones desde este '
             'diario (lo usa el lote de pagos al generar el archivo del banco).',
    )

    @api.depends('kenocia_sequence_ids')
    def _compute_kenocia_sequence_count(self):
        for journal in self:
            journal.kenocia_sequence_count = len(journal.kenocia_sequence_ids)

    @api.depends(
        'payment_sequence',
        'kenocia_sequence_ids.active',
        'kenocia_sequence_ids.transaction_type',
    )
    def _compute_kenocia_cheque_native_seq_coexist(self):
        for journal in self:
            has_active_cheque_seq = any(
                seq.active and seq.transaction_type == 'cheque'
                for seq in journal.kenocia_sequence_ids
            )
            journal.kenocia_cheque_native_seq_coexist = bool(
                journal.payment_sequence and has_active_cheque_seq
            )

    @api.depends(
        'type',
        'inbound_payment_method_line_ids.payment_account_id',
        'outbound_payment_method_line_ids.payment_account_id',
    )
    def _compute_kenocia_missing_payment_account(self):
        for journal in self:
            if journal.type not in ('bank', 'cash'):
                journal.kenocia_missing_payment_account = False
                continue
            method_lines = (
                journal.inbound_payment_method_line_ids
                | journal.outbound_payment_method_line_ids
            )
            journal.kenocia_missing_payment_account = any(
                not line.payment_account_id for line in method_lines
            )

    def action_view_kenocia_sequences(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Secuencias de Tesorería'),
            'res_model': 'kenocia.sequence',
            'view_mode': 'list,form',
            'domain': [('journal_id', '=', self.id)],
            'context': {'default_journal_id': self.id},
        }

    def action_kenocia_create_sequence(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nueva secuencia'),
            'res_model': 'kenocia.sequence',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_journal_id': self.id},
        }
