# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3
"""Núcleo de dispersión compartido por los 3 escenarios de pago masivo.

Recibe especificaciones por beneficiario y:
  1. Crea UN pago por beneficiario (account.payment) por el total asignado.
  2. Concilia (parcial controlada) la línea del pago contra cada línea por
     cobrar/pagar seleccionada, respetando el monto exacto por línea.
  3. (Opcional) Agrupa los pagos en un account.batch.payment nativo.

Cada `spec` es un dict con:
    - partner:       res.partner del beneficiario
    - partner_type:  'customer' | 'supplier'
    - payment_type:  'inbound'  | 'outbound'
    - account:       account.account por cobrar/pagar (donde se concilia)
    - allocations:   lista de tuplas (account.move.line, monto)
    - memo:          (opcional) texto del pago
"""

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class KenociaDispersionEngine(models.AbstractModel):
    _name = 'kenocia.dispersion.engine'
    _description = 'Motor de Dispersión / Pagos Masivos KENOCIA'

    @api.model
    def kenocia_run_dispersion(
        self, specs, journal, date, memo=False,
        tesoreria_type=False, group_into_batch=True, batch_label=False,
        batch_tesoreria_type=False,
    ):
        """Punto de entrada único. Devuelve dict con payments y batch.

        Opción A (1 depósito = 1 correlativo): los pagos individuales usan la
        numeración nativa del diario (``tesoreria_type`` normalmente vacío) y el
        LOTE recibe UN correlativo Kenocia según ``batch_tesoreria_type`` si el
        diario tiene una secuencia activa para ese tipo.
        """
        if not specs:
            raise UserError(_('No hay líneas seleccionadas para dispersar.'))
        if not journal or journal.type not in ('bank', 'cash'):
            raise UserError(_('Debe seleccionar un diario de banco o efectivo.'))

        payments = self.env['account.payment']
        for spec in specs:
            payments |= self._kenocia_create_single_payment(
                spec, journal, date, memo=memo, tesoreria_type=tesoreria_type,
            )

        batch = self.env['account.batch.payment']
        if group_into_batch and payments:
            batch = self._kenocia_group_into_batch(
                payments, journal, date, label=batch_label,
            )
            if batch and batch_tesoreria_type:
                batch._kenocia_assign_sequence(batch_tesoreria_type)
        return {'payments': payments, 'batch': batch}

    # ------------------------------------------------------------------
    # Creación + conciliación de un pago
    # ------------------------------------------------------------------
    @api.model
    def _kenocia_create_single_payment(
        self, spec, journal, date, memo=False, tesoreria_type=False,
    ):
        partner = spec['partner']
        account = spec['account']
        allocations = [
            (line, amount) for line, amount in spec['allocations']
            if amount and not float_is_zero(
                amount, precision_rounding=line.company_currency_id.rounding,
            )
        ]
        if not allocations:
            raise UserError(_(
                'El beneficiario %(name)s no tiene montos a pagar.',
                name=partner.display_name,
            ))

        currency = self._kenocia_validate_currency(allocations, journal)
        total = sum(amount for _line, amount in allocations)

        payment_vals = {
            'payment_type': spec['payment_type'],
            'partner_type': spec['partner_type'],
            'partner_id': partner.id,
            'amount': total,
            'currency_id': currency.id,
            'date': date,
            'journal_id': journal.id,
            'destination_account_id': account.id,
            'memo': memo or spec.get('memo') or '',
        }
        if tesoreria_type:
            payment_vals['tesoreria_type'] = tesoreria_type

        payment = self.env['account.payment'].create(payment_vals)
        # Reforzamos la cuenta destino por si el compute la recalculó.
        if payment.destination_account_id != account:
            payment.destination_account_id = account.id
        payment.action_post()

        pay_line = payment.move_id.line_ids.filtered(
            lambda l: l.account_id == account and not l.reconciled,
        )[:1]
        if not pay_line:
            raise UserError(_(
                'No se generó la línea conciliable del pago para %(name)s. '
                'Verifique la cuenta destino y la cuenta puente del diario.',
                name=partner.display_name,
            ))

        for line, amount in allocations:
            self._kenocia_partial_reconcile(pay_line, line, amount)
        return payment

    # ------------------------------------------------------------------
    # Conciliación parcial controlada por monto exacto
    # ------------------------------------------------------------------
    @api.model
    def _kenocia_partial_reconcile(self, line_a, line_b, amount):
        if line_a.account_id != line_b.account_id:
            raise UserError(_(
                'No se puede conciliar líneas de cuentas distintas '
                '(%(a)s vs %(b)s).',
                a=line_a.account_id.display_name,
                b=line_b.account_id.display_name,
            ))
        if line_a.balance > 0:
            debit_line, credit_line = line_a, line_b
        else:
            debit_line, credit_line = line_b, line_a
        self.env['account.partial.reconcile'].create({
            'debit_move_id': debit_line.id,
            'credit_move_id': credit_line.id,
            'amount': amount,
            'debit_amount_currency': amount,
            'credit_amount_currency': amount,
        })

    # ------------------------------------------------------------------
    # Agrupación en lote nativo (best-effort)
    # ------------------------------------------------------------------
    @api.model
    def _kenocia_group_into_batch(self, payments, journal, date, label=False):
        """Agrupa los pagos en un lote (best-effort).

        El lote es opcional: solo se usa para el archivo del banco (Fase 2) y la
        conciliación bancaria de un solo movimiento. Si el diario no tiene un
        método de pago apto para lote, NO se interrumpe la dispersión: los pagos
        ya quedaron creados y conciliados.
        """
        empty = self.env['account.batch.payment']
        batch_type = payments[:1].payment_type
        method = payments.payment_method_id
        if len(method) != 1:
            return empty
        # El método debe estar entre los disponibles para lote en el diario.
        available_methods = journal._get_available_payment_method_lines(
            batch_type,
        ).payment_method_id
        if method not in available_methods:
            return empty
        vals = {
            'journal_id': journal.id,
            'payment_ids': [(6, 0, payments.ids)],
            'payment_method_id': method.id,
            'batch_type': batch_type,
            'date': date,
        }
        if label:
            vals['name'] = label
        try:
            with self.env.cr.savepoint():
                batch = self.env['account.batch.payment'].create(vals)
        except Exception:
            # Configuración de lote no apta: continuamos sin lote.
            return empty
        return batch

    # ------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------
    @api.model
    def _kenocia_validate_currency(self, allocations, journal):
        """v1: exige misma moneda en líneas, diario y compañía."""
        company_currency = journal.company_id.currency_id
        journal_currency = journal.currency_id or company_currency
        for line, _amount in allocations:
            line_currency = line.currency_id or company_currency
            if line_currency != journal_currency:
                raise UserError(_(
                    'Multimoneda no soportada en esta versión: la línea '
                    '%(line)s está en %(lc)s y el diario en %(jc)s.',
                    line=line.move_id.display_name,
                    lc=line_currency.name,
                    jc=journal_currency.name,
                ))
        return journal_currency

    @api.model
    def kenocia_check_allocation_amount(self, line, amount):
        """Valida que el monto a aplicar no exceda el saldo de la línea."""
        rounding = line.company_currency_id.rounding
        residual = abs(line.amount_residual)
        if float_compare(amount, 0.0, precision_rounding=rounding) < 0:
            raise UserError(_('El monto a pagar no puede ser negativo.'))
        if float_compare(amount, residual, precision_rounding=rounding) > 0:
            raise UserError(_(
                'El monto a pagar (%(amount)s) supera el saldo pendiente '
                '(%(residual)s) de %(doc)s.',
                amount=amount, residual=residual,
                doc=line.move_id.display_name,
            ))
