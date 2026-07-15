# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class KenociaPettyCashRecharge(models.Model):
    _name = 'kenocia.petty.cash.recharge'
    _description = 'Recarga de Fondo de Caja Chica'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    petty_cash_id = fields.Many2one(
        comodel_name='kenocia.petty.cash',
        string='Fondo',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    name = fields.Char(
        string='Referencia',
        readonly=True,
        copy=False,
        default=lambda self: _('Nueva Recarga'),
        tracking=True,
    )
    date = fields.Date(
        string='Fecha',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    amount = fields.Monetary(
        string='Monto recarga',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    journal_source_id = fields.Many2one(
        comodel_name='account.journal',
        string='Banco origen',
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
        required=True,
        tracking=True,
        help='Banco desde donde se emite el cheque o transferencia.',
    )
    reference = fields.Char(
        string='N° cheque / referencia',
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('in_transit', 'En tránsito'),
            ('received', 'Efectivo recibido'),
            ('cancelled', 'Cancelado'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
    )
    payment_bank_id = fields.Many2one(
        comodel_name='account.payment',
        string='Pago banco → tránsito',
        readonly=True,
        copy=False,
    )
    move_receipt_id = fields.Many2one(
        comodel_name='account.move',
        string='Asiento tránsito → caja',
        readonly=True,
        copy=False,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='petty_cash_id.company_id',
        store=True,
        index=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='petty_cash_id.currency_id',
        store=True,
    )

    _sql_constraints = [
        (
            'positive_amount',
            'CHECK(amount > 0)',
            'El monto de la recarga debe ser mayor a cero.',
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nueva Recarga')) in (_('Nueva Recarga'), 'Nueva Recarga', '/'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'kenocia.petty.cash.recharge',
                ) or _('Nueva Recarga')
        return super().create(vals_list)

    def _check_supervisor_or_cxp(self):
        user = self.env.user
        if not (
            user.has_group('kenocia_tesoreria_v18.group_tesoreria_supervisor')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_admin')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_cxp')
        ):
            raise AccessError(_(
                'Solo supervisor, administrador o tesorería CXP puede registrar '
                'recargas bancarias.',
            ))

    def _check_custodian_access(self):
        if not self.petty_cash_id._kenocia_user_can_manage_petty_cash():
            raise AccessError(_(
                'No tiene permiso para confirmar recepción de efectivo.',
            ))

    def _create_and_post_transit_payment(self, fund, memo):
        """Banco → tránsito: DEBE puente, HABER cuenta bancaria."""
        self.ensure_one()
        bank_account = self.journal_source_id.default_account_id
        if not bank_account:
            raise UserError(_(
                'El diario %(journal)s no tiene cuenta bancaria predeterminada.',
                journal=self.journal_source_id.display_name,
            ))
        payment = self.env['account.payment'].with_context(
            kenocia_petty_cash=True,
        ).create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': fund.company_id.partner_id.id,
            'journal_id': self.journal_source_id.id,
            'amount': self.amount,
            'date': self.date,
            'memo': memo,
            'destination_account_id': fund.account_bridge_id.id,
            'currency_id': self.currency_id.id,
        })
        # Odoo 18 usa outstanding_account_id como contrapartida de liquidez;
        # forzamos la cuenta del banco para obtener DEBE puente / HABER banco.
        payment.write({'outstanding_account_id': bank_account.id})
        payment._kenocia_generate_and_post_move()
        if payment.state in ('draft', 'in_process'):
            payment.action_validate()
        return payment

    def action_send_to_transit(self):
        for recharge in self:
            recharge._check_supervisor_or_cxp()
            if recharge.state != 'draft':
                raise UserError(_('Solo recargas en borrador pueden enviarse a tránsito.'))
            fund = recharge.petty_cash_id
            if fund.state != 'open':
                raise UserError(_('El fondo debe estar abierto para registrar recargas.'))
            if not fund.account_bridge_id:
                raise UserError(_('Configure la cuenta puente del fondo.'))

            memo = _(
                'Recarga caja chica: %(fund)s %(ref)s',
                fund=fund.name,
                ref=recharge.reference or '',
            ).strip()
            payment = recharge._create_and_post_transit_payment(fund, memo)
            recharge.write({
                'payment_bank_id': payment.id,
                'state': 'in_transit',
            })
            recharge.message_post(
                body=_(
                    'Recarga enviada a tránsito. Monto: <b>%(amount)s</b>. '
                    'Referencia: <b>%(ref)s</b>. Pago: <b>%(pay)s</b>.',
                    amount=recharge.currency_id.format(recharge.amount),
                    ref=recharge.reference or _('N/A'),
                    pay=payment.display_name,
                ),
                subtype_xmlid='mail.mt_note',
            )
            fund.message_post(
                body=_(
                    'Recarga <b>%(name)s</b> en tránsito por <b>%(amount)s</b>.',
                    name=recharge.name,
                    amount=recharge.currency_id.format(recharge.amount),
                ),
                subtype_xmlid='mail.mt_note',
            )
        return True

    def action_confirm_cash_received(self):
        for recharge in self:
            recharge._check_custodian_access()
            if recharge.state != 'in_transit':
                raise UserError(_(
                    'Solo recargas en tránsito pueden confirmarse como recibidas.',
                ))
            fund = recharge.petty_cash_id
            cash_account = fund.journal_id.default_account_id
            if not cash_account:
                raise UserError(_(
                    'El diario %(journal)s no tiene cuenta predeterminada configurada.',
                    journal=fund.journal_id.display_name,
                ))
            move = self.env['account.move'].create({
                'journal_id': fund.journal_id.id,
                'date': fields.Date.context_today(recharge),
                'ref': _('Recepción efectivo - Recarga %(name)s', name=recharge.name),
                'line_ids': [
                    (0, 0, {
                        'account_id': cash_account.id,
                        'debit': recharge.amount,
                        'credit': 0.0,
                        'name': _('Recarga caja chica - %(fund)s', fund=fund.name),
                    }),
                    (0, 0, {
                        'account_id': fund.account_bridge_id.id,
                        'debit': 0.0,
                        'credit': recharge.amount,
                        'name': _('Liquidación tránsito - %(fund)s', fund=fund.name),
                    }),
                ],
            })
            move.action_post()
            recharge.write({
                'move_receipt_id': move.id,
                'state': 'received',
            })
            recharge.message_post(
                body=_(
                    'Efectivo recibido físicamente. Asiento: <b>%(move)s</b>. '
                    'Saldo disponible del fondo actualizado.',
                    move=move.display_name,
                ),
                subtype_xmlid='mail.mt_note',
            )
            fund.message_post(
                body=_(
                    'Recarga <b>%(name)s</b> confirmada. '
                    'Disponible del fondo: <b>%(avail)s</b>.',
                    name=recharge.name,
                    avail=fund.currency_id.format(fund.amount_available),
                ),
                subtype_xmlid='mail.mt_note',
            )
        return True

    def action_cancel(self):
        for recharge in self:
            if recharge.state == 'received':
                raise UserError(_('No se puede cancelar una recarga ya recibida.'))
            if recharge.state == 'in_transit' and recharge.payment_bank_id:
                if recharge.payment_bank_id.state != 'canceled':
                    recharge.payment_bank_id.action_cancel()
            recharge.write({'state': 'cancelled'})
            recharge.message_post(
                body=_('Recarga cancelada.'),
                subtype_xmlid='mail.mt_note',
            )
        return True
