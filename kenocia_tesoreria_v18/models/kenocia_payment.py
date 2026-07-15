# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    tesoreria_type = fields.Selection(
        selection=[
            ('cheque', 'Cheque'),
            ('deposito', 'Depósito'),
            ('debito', 'Débito'),
            ('credito', 'Crédito'),
            ('transferencia', 'Transferencia'),
            ('transferencia_banco', 'Transferencia Bancaria'),
            ('efectivo', 'Efectivo'),
        ],
        string='Tipo tesorería',
        tracking=True,
        copy=False,
        help='Activa el flujo de correlativo KENOCIA al confirmar el pago.',
    )
    kenocia_seq_id = fields.Many2one(
        comodel_name='kenocia.sequence',
        string='Secuencia tesorería',
        readonly=True,
        copy=False,
        tracking=True,
    )
    kenocia_sequence_name = fields.Char(
        string='Correlativo tesorería',
        readonly=True,
        copy=False,
        tracking=True,
    )
    is_reconciled_tesoreria = fields.Boolean(
        string='Conciliado tesorería',
        compute='_compute_is_reconciled_tesoreria',
        store=True,
    )
    state_tesoreria = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('posted', 'Publicado'),
            ('reconciled', 'Conciliado'),
            ('void', 'Anulado'),
            ('cancelled', 'Cancelado'),
        ],
        string='Estado tesorería',
        compute='_compute_state_tesoreria',
        store=True,
    )
    is_void_cheque = fields.Boolean(
        string='Cheque anulado',
        default=False,
        copy=False,
        tracking=True,
    )
    void_reason = fields.Text(
        string='Motivo de anulación',
        tracking=True,
        copy=False,
    )
    amount_in_words = fields.Char(
        string='Monto en letras',
        compute='_compute_amount_in_words',
    )
    advance_ids = fields.One2many(
        comodel_name='kenocia.advance.payment',
        inverse_name='payment_id',
        string='Adelantos vinculados',
    )
    advance_count = fields.Integer(
        string='Cantidad de adelantos',
        compute='_compute_advance_count',
    )
    advance_invoice_count = fields.Integer(
        string='Facturas del anticipo',
        compute='_compute_advance_invoice_count',
    )
    petty_cash_line_id = fields.Many2one(
        comodel_name='kenocia.petty.cash.line',
        string='Anticipo caja chica',
        readonly=True,
        copy=False,
        tracking=True,
    )

    @api.depends('advance_ids')
    def _compute_advance_count(self):
        for payment in self:
            payment.advance_count = len(payment.advance_ids)

    @api.depends('advance_ids.invoice_ids')
    def _compute_advance_invoice_count(self):
        for payment in self:
            payment.advance_invoice_count = len(
                payment.advance_ids.mapped('invoice_ids'),
            )

    @api.depends('amount', 'currency_id')
    def _compute_amount_in_words(self):
        for payment in self:
            if payment.currency_id and payment.amount:
                payment.amount_in_words = payment.currency_id.amount_to_text(
                    payment.amount,
                )
            else:
                payment.amount_in_words = False

    @api.depends('is_reconciled', 'tesoreria_type')
    def _compute_is_reconciled_tesoreria(self):
        for payment in self:
            payment.is_reconciled_tesoreria = bool(
                payment.tesoreria_type and payment.is_reconciled,
            )

    @api.depends('state', 'is_reconciled_tesoreria', 'is_void_cheque', 'tesoreria_type')
    def _compute_state_tesoreria(self):
        for payment in self:
            if not payment.tesoreria_type:
                payment.state_tesoreria = False
            elif payment.is_void_cheque:
                payment.state_tesoreria = 'void'
            elif payment.state == 'canceled':
                payment.state_tesoreria = 'cancelled'
            elif payment.is_reconciled_tesoreria:
                payment.state_tesoreria = 'reconciled'
            elif payment.state in ('in_process', 'paid'):
                payment.state_tesoreria = 'posted'
            else:
                payment.state_tesoreria = 'draft'

    @api.model
    def _kenocia_user_can_manage_cxc(self):
        user = self.env.user
        return (
            user.has_group('kenocia_tesoreria_v18.group_tesoreria_cxc')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_supervisor')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_admin')
        )

    @api.model
    def _kenocia_user_can_manage_cxp(self):
        user = self.env.user
        return (
            user.has_group('kenocia_tesoreria_v18.group_tesoreria_cxp')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_supervisor')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_admin')
        )

    @api.model
    def _kenocia_user_can_manage_petty_cash(self):
        user = self.env.user
        return (
            user.has_group('kenocia_tesoreria_v18.group_tesoreria_custodian')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_supervisor')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_admin')
        )

    @api.model
    def _check_payment_type_role(self, payment_type):
        if not payment_type:
            return
        if (
            self.env.context.get('kenocia_petty_cash')
            and self._kenocia_user_can_manage_petty_cash()
        ):
            return
        has_tesoreria = (
            self.env.user.has_group('kenocia_tesoreria_v18.group_tesoreria_cxc')
            or self.env.user.has_group('kenocia_tesoreria_v18.group_tesoreria_cxp')
            or self.env.user.has_group('kenocia_tesoreria_v18.group_tesoreria_supervisor')
            or self.env.user.has_group('kenocia_tesoreria_v18.group_tesoreria_admin')
        )
        if not has_tesoreria:
            return
        if payment_type == 'inbound' and not self._kenocia_user_can_manage_cxc():
            raise AccessError(_(
                'No tiene permiso para registrar cobros entrantes (CXC).',
            ))
        if payment_type == 'outbound' and not self._kenocia_user_can_manage_cxp():
            raise AccessError(_(
                'No tiene permiso para registrar pagos salientes (CXP).',
            ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_payment_type_role(vals.get('payment_type'))
        return super().create(vals_list)

    def write(self, vals):
        if 'payment_type' in vals:
            self._check_payment_type_role(vals['payment_type'])
        if 'tesoreria_type' in vals:
            for payment in self:
                if payment.state in ('in_process', 'paid', 'canceled'):
                    if vals['tesoreria_type'] != payment.tesoreria_type:
                        raise ValidationError(_(
                            'No puede cambiar el tipo de tesorería de un pago '
                            'que ya fue publicado o cancelado.',
                        ))
        return super().write(vals)

    @api.depends(
        'payment_type', 'partner_type', 'partner_id', 'company_id',
        'advance_ids.advance_account_id',
    )
    def _compute_destination_account_id(self):
        super()._compute_destination_account_id()
        for payment in self.filtered('advance_ids'):
            advance_account = payment.advance_ids[:1].advance_account_id
            if advance_account:
                payment.destination_account_id = advance_account

    def _kenocia_ensure_outstanding_account(self):
        """Odoo 18 requiere cuenta outstanding para generar el asiento."""
        for payment in self.filtered(lambda p: not p.outstanding_account_id):
            outstanding = payment._get_outstanding_account(payment.payment_type)
            payment.outstanding_account_id = outstanding.id

    def _kenocia_generate_and_post_move(self):
        """Genera y publica el asiento contable del pago (Odoo 18)."""
        for payment in self:
            payment._kenocia_ensure_outstanding_account()
            if not payment.move_id:
                payment._generate_journal_entry()
            if payment.move_id and payment.move_id.state == 'draft':
                payment.move_id.action_post()

    def action_validate(self):
        advance_payments = self.filtered(
            lambda p: p.advance_ids and not p.move_id,
        )
        advance_payments._kenocia_generate_and_post_move()
        return super().action_validate()

    def _get_kenocia_sequence(self):
        self.ensure_one()
        return self.env['kenocia.sequence'].search([
            ('journal_id', '=', self.journal_id.id),
            ('transaction_type', '=', self.tesoreria_type),
            ('active', '=', True),
        ], limit=1)

    def _kenocia_prepare_sequence_before_post(self):
        treasury_payments = self.filtered('tesoreria_type')
        for payment in treasury_payments:
            # Idempotente: si el pago ya tiene correlativo (p.ej. se regresó a
            # borrador y se vuelve a publicar), se conserva y NO se quema un
            # número nuevo. Así el cheque siempre gana al re-publicar.
            if payment.kenocia_sequence_name:
                continue
            sequence = payment._get_kenocia_sequence()
            if not sequence:
                # Comportamiento nativo de Odoo: si no hay secuencia Kenocia
                # activa para (diario, tipo), el pago se numera con la
                # secuencia estándar del diario y NO se bloquea.
                continue
            generated = sequence.generate_next()
            payment.write({
                'kenocia_seq_id': sequence.id,
                'kenocia_sequence_name': generated,
            })

    def _kenocia_sync_move_sequence_name(self):
        for payment in self.filtered(
            lambda p: p.tesoreria_type and p.kenocia_sequence_name and p.move_id,
        ):
            if payment.move_id.name != payment.kenocia_sequence_name:
                payment.move_id.name = payment.kenocia_sequence_name

    def _generate_move_vals(self, write_off_line_vals=None, force_balance=None, line_ids=None):
        move_vals = super()._generate_move_vals(
            write_off_line_vals=write_off_line_vals,
            force_balance=force_balance,
            line_ids=line_ids,
        )
        if self.tesoreria_type and self.kenocia_sequence_name:
            move_vals['name'] = self.kenocia_sequence_name
        return move_vals

    def action_post(self):
        treasury_payments = self.filtered('tesoreria_type')
        treasury_payments._kenocia_prepare_sequence_before_post()
        res = super().action_post()
        treasury_payments._kenocia_sync_move_sequence_name()
        for payment in treasury_payments.filtered('kenocia_sequence_name'):
            payment.message_post(
                body=_(
                    'Pago confirmado con secuencia tesorería '
                    '<b>%(seq)s</b> (tipo: %(type)s).',
                    seq=payment.kenocia_sequence_name,
                    type=dict(payment._fields['tesoreria_type'].selection).get(
                        payment.tesoreria_type, payment.tesoreria_type,
                    ),
                ),
                subtype_xmlid='mail.mt_note',
            )
        return res

    def action_void_cheque(self):
        self.ensure_one()
        self._check_void_cheque_access()
        if self.tesoreria_type != 'cheque':
            raise UserError(_('Solo se pueden anular pagos de tipo Cheque.'))
        if self.state not in ('draft', 'in_process', 'paid'):
            raise UserError(_(
                'Solo se pueden anular cheques en estado Borrador o Publicado.',
            ))
        if self.is_void_cheque:
            raise UserError(_('Este cheque ya fue anulado.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Anular Cheque'),
            'res_model': 'kenocia.void.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_payment_id': self.id},
        }

    def _check_void_cheque_access(self):
        if not self.env.user.has_group('kenocia_tesoreria_v18.group_tesoreria_supervisor'):
            raise UserError(_(
                'Solo un Supervisor o Administrador de Tesorería puede anular cheques.',
            ))

    def _action_void_cheque_confirm(self, reason):
        self.ensure_one()
        self._check_void_cheque_access()
        if not reason or not reason.strip():
            raise UserError(_('Debe indicar el motivo de anulación.'))

        voided_number = self.kenocia_sequence_name or self.name
        if self.kenocia_seq_id and voided_number:
            self.kenocia_seq_id.register_void(voided_number, reason=reason.strip())

        previous_state = self.state
        if self.state != 'draft':
            super().action_cancel()

        self.write({
            'is_void_cheque': True,
            'void_reason': reason.strip(),
        })
        self.message_post(
            body=_(
                'Cheque <b>ANULADO</b>. Número: <b>%(number)s</b>. '
                'Motivo: %(reason)s. El correlativo no será reutilizado.',
                number=voided_number or _('N/A'),
                reason=reason.strip(),
            ),
            subtype_xmlid='mail.mt_note',
        )
        return previous_state

    def action_open_advance_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Adelantos vinculados'),
            'res_model': 'kenocia.advance.payment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.advance_ids.ids)],
            'context': {'create': False},
        }

    def action_open_advance_invoices(self):
        """Facturas finales donde se aplicó el anticipo de este pago."""
        self.ensure_one()
        invoice_ids = self.advance_ids.mapped('invoice_ids').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Facturas del anticipo'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoice_ids)],
            'context': {'create': False},
        }

    _KENOCIA_TESORERIA_FORM_VIEWS = {
        'cheque': 'kenocia_tesoreria_v18.view_kenocia_payment_cheque_form',
        'transferencia': 'kenocia_tesoreria_v18.view_kenocia_payment_transfer_form',
        'transferencia_banco': 'kenocia_tesoreria_v18.view_kenocia_payment_transfer_form',
        'efectivo': 'kenocia_tesoreria_v18.view_kenocia_payment_cash_form',
    }

    def get_formview_id(self, access_uid=None):
        self.ensure_one()
        view_xmlid = self._KENOCIA_TESORERIA_FORM_VIEWS.get(self.tesoreria_type)
        if view_xmlid:
            return self.env.ref(view_xmlid).id
        return super().get_formview_id(access_uid=access_uid)

    def _get_kenocia_payment_receipt_partner(self):
        """Contacto para el recibo: pago, documentos conciliados o anticipo."""
        self.ensure_one()
        if self.partner_id:
            return self.partner_id
        for doc in self._get_kenocia_payment_receipt_documents():
            if doc.get('partner'):
                return doc['partner']
        if self.advance_ids:
            return self.advance_ids[:1].partner_id
        return self.env['res.partner']

    def _get_kenocia_payment_receipt_documents(self):
        """Documentos conciliados al pago, incluidos asientos de apertura (entry)."""
        self.ensure_one()
        if not self.move_id:
            return []

        doc_amounts = {}
        payable_lines = self.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type in (
                'asset_receivable', 'liability_payable',
            ),
        )
        for pay_line in payable_lines:
            partials = pay_line.matched_debit_ids | pay_line.matched_credit_ids
            for partial in partials:
                if partial.debit_move_id == pay_line:
                    counterpart = partial.credit_move_id
                    amount = partial.credit_amount_currency or partial.amount
                else:
                    counterpart = partial.debit_move_id
                    amount = partial.debit_amount_currency or partial.amount

                move = counterpart.move_id
                key = move.id
                if key not in doc_amounts:
                    doc_amounts[key] = {
                        'move': move,
                        'date': move.invoice_date or move.date,
                        'name': move.name,
                        'ref': move.ref or move.payment_reference or '',
                        'amount': 0.0,
                        'currency': move.currency_id or self.currency_id,
                        'partner': move.partner_id or counterpart.partner_id,
                    }
                doc_amounts[key]['amount'] += abs(amount)

        return sorted(
            doc_amounts.values(),
            key=lambda doc: (doc['date'] or '', doc['name'] or ''),
        )

    def _get_payment_receipt_report_values(self):
        values = super()._get_payment_receipt_report_values()
        self.ensure_one()
        receipt_documents = self._get_kenocia_payment_receipt_documents()
        values['receipt_partner'] = self._get_kenocia_payment_receipt_partner()
        values['receipt_documents'] = receipt_documents
        if receipt_documents:
            values['display_invoices'] = True
        return values
