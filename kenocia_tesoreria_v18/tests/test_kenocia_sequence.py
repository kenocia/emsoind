# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from unittest.mock import patch

from psycopg2 import IntegrityError, OperationalError

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, mute_logger


@tagged('post_install', '-at_install')
class TestKenociaSequence(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal_bank = cls.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)
        if not cls.journal_bank:
            cls.journal_bank = cls.env['account.journal'].create({
                'name': 'Banco Test Tesorería',
                'type': 'bank',
                'code': 'KTBN',
            })

    def _create_sequence(self, **kwargs):
        values = {
            'name': 'Secuencia Test',
            'journal_id': self.journal_bank.id,
            'transaction_type': 'cheque',
            'prefix': 'CHQ/TEST/',
            'next_number': 1,
            'padding': 4,
        }
        values.update(kwargs)
        return self.env['kenocia.sequence'].create(values)

    def test_sequence_generates_correct_format(self):
        """TEST-01: CHQ/TEST/0001 → next=2, last_generated=CHQ/TEST/0001."""
        sequence = self._create_sequence()
        generated = sequence.generate_next()
        self.assertEqual(generated, 'CHQ/TEST/0001')
        self.assertEqual(sequence.next_number, 2)
        self.assertEqual(sequence.last_generated, 'CHQ/TEST/0001')
        self.assertEqual(sequence.preview, 'CHQ/TEST/0002')

    def test_sequence_lock_prevents_duplicates(self):
        """TEST-02: lock NOWAIT bloquea generación concurrente."""
        sequence = self._create_sequence()
        original_execute = self.env.cr.execute

        def execute_with_lock_error(query, params=None, log_exceptions=True):
            if isinstance(query, str) and 'FOR UPDATE NOWAIT' in query:
                raise OperationalError('could not obtain lock')
            return original_execute(query, params, log_exceptions)

        with patch.object(self.env.cr, 'execute', side_effect=execute_with_lock_error):
            raised_user_error = False
            try:
                sequence.generate_next()
            except UserError:
                raised_user_error = True
        self.assertTrue(raised_user_error)
        self.assertEqual(sequence.next_number, 1)
        self.assertFalse(sequence.last_generated)

    def test_sequence_unique_constraint(self):
        """TEST-03: no se permiten dos secuencias del mismo tipo en un diario."""
        self._create_sequence()
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self._create_sequence(name='Secuencia Duplicada')

    def test_inactive_sequence_raises_user_error(self):
        sequence = self._create_sequence(active=False)
        with self.assertRaises(UserError):
            sequence.generate_next()

    def test_register_void_increments_void_count(self):
        sequence = self._create_sequence()
        generated = sequence.generate_next()
        sequence.register_void(generated, reason='Cheque dañado')
        self.assertEqual(sequence.void_count, 1)
