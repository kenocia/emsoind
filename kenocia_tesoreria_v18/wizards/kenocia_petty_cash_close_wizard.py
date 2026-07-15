# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class KenociaPettyCashCloseWizard(models.TransientModel):
    _name = 'kenocia.petty.cash.close.wizard'
    _description = 'Wizard — Cierre de Fondo Caja Chica'

    fund_id = fields.Many2one(
        comodel_name='kenocia.petty.cash',
        string='Fondo',
        required=True,
        readonly=True,
    )
    amount_system = fields.Monetary(
        string='Saldo según sistema',
        related='fund_id.amount_available',
        readonly=True,
    )
    amount_physical = fields.Monetary(
        string='Saldo físico contado',
        required=True,
        currency_field='currency_id',
        help='Monto físico contado en la caja al momento del cierre.',
    )
    amount_difference = fields.Monetary(
        string='Diferencia (sobrante / faltante)',
        compute='_compute_difference',
        currency_field='currency_id',
    )
    journal_return_id = fields.Many2one(
        comodel_name='account.journal',
        string='Depositar saldo en',
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
        required=True,
    )
    notes = fields.Text(string='Observaciones del arqueo')
    currency_id = fields.Many2one(
        related='fund_id.currency_id',
    )
    company_id = fields.Many2one(
        related='fund_id.company_id',
    )
    move_return_id = fields.Many2one(
        comodel_name='account.move',
        string='Asiento devolución',
        readonly=True,
    )

    @api.depends('amount_system', 'amount_physical')
    def _compute_difference(self):
        for wizard in self:
            wizard.amount_difference = wizard.amount_physical - wizard.amount_system

    @api.onchange('amount_system')
    def _onchange_amount_system(self):
        if self.amount_system and not self.amount_physical:
            self.amount_physical = self.amount_system

    def action_confirm_close(self):
        self.ensure_one()
        fund = self.fund_id
        user = self.env.user
        if not (
            user.has_group('kenocia_tesoreria_v18.group_tesoreria_supervisor')
            or user.has_group('kenocia_tesoreria_v18.group_tesoreria_admin')
        ):
            raise AccessError(_(
                'Solo supervisores o administradores pueden cerrar fondos.',
            ))
        if fund.state != 'open':
            raise UserError(_('Solo se pueden cerrar fondos en estado Abierto.'))
        if fund.recharge_in_transit_count:
            raise UserError(_(
                'No se puede cerrar el fondo mientras haya recargas en tránsito.',
            ))

        pending_advances = fund.line_ids.filtered(lambda line: line.state == 'delivered')
        if pending_advances:
            names = ', '.join(pending_advances.mapped('employee_id.display_name'))
            raise UserError(_(
                'No se puede cerrar el fondo. Existen %(count)s anticipo(s) '
                'sin liquidar:\n%(names)s\n\n'
                'Liquide todos los anticipos con su factura SAR antes de cerrar.',
                count=len(pending_advances),
                names=names,
            ))

        bank_account = self.journal_return_id.default_account_id
        cash_account = fund.journal_id.default_account_id
        if self.amount_system > 0:
            if not bank_account:
                raise UserError(_(
                    'El diario bancario %(journal)s no tiene cuenta predeterminada.',
                    journal=self.journal_return_id.display_name,
                ))
            if not cash_account:
                raise UserError(_(
                    'El diario de caja %(journal)s no tiene cuenta predeterminada.',
                    journal=fund.journal_id.display_name,
                ))
            move = self.env['account.move'].create({
                'journal_id': self.journal_return_id.id,
                'date': fields.Date.context_today(self),
                'ref': _('Cierre fondo caja chica: %(fund)s', fund=fund.name),
                'line_ids': [
                    (0, 0, {
                        'account_id': bank_account.id,
                        'debit': self.amount_system,
                        'credit': 0.0,
                        'name': _('Devolución saldo - %(fund)s', fund=fund.name),
                    }),
                    (0, 0, {
                        'account_id': cash_account.id,
                        'debit': 0.0,
                        'credit': self.amount_system,
                        'name': _('Cierre caja chica - %(fund)s', fund=fund.name),
                    }),
                ],
            })
            move.action_post()
            self.move_return_id = move.id

        fund.write({
            'state': 'closed',
            'close_physical_amount': self.amount_physical,
            'close_difference_amount': self.amount_difference,
            'close_return_journal_id': self.journal_return_id.id,
            'close_move_return_id': self.move_return_id.id,
            'close_notes': self.notes,
            'close_user_id': user.id,
            'close_date': fields.Datetime.now(),
        })
        fund.message_post(
            body=_(
                '<b>Fondo cerrado.</b><br/>'
                'Fecha cierre: %(date)s<br/>'
                'Saldo sistema: <b>%(system)s</b><br/>'
                'Saldo físico contado: <b>%(physical)s</b><br/>'
                'Diferencia: <b>%(diff)s</b><br/>'
                'Depositado en: %(bank)s<br/>'
                'Asiento devolución: %(move)s<br/>'
                'Cerrado por: %(user)s<br/>'
                'Observaciones: %(notes)s',
                date=fields.Datetime.now(),
                system=fund.currency_id.format(self.amount_system),
                physical=fund.currency_id.format(self.amount_physical),
                diff=fund.currency_id.format(self.amount_difference),
                bank=self.journal_return_id.display_name,
                move=self.move_return_id.display_name if self.move_return_id else _('N/A'),
                user=user.display_name,
                notes=self.notes or _('Ninguna'),
            ),
            subtype_xmlid='mail.mt_note',
        )
        return {'type': 'ir.actions.act_window_close'}
