# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class KcExpenseAdvanceCloseWizard(models.TransientModel):
    _name = 'kc.expense.advance.close.wizard'
    _description = 'Wizard Cierre de Anticipo con Diferencia'

    advance_id = fields.Many2one(
        'kc.expense.advance',
        required=True,
        readonly=True,
    )
    amount_balance = fields.Monetary(readonly=True)
    currency_id = fields.Many2one(related='advance_id.currency_id')
    close_type = fields.Selection(
        selection=[
            ('balanced', 'Cuadrado'),
            ('surplus', 'Sobrante (vuelto)'),
            ('deficit', 'Faltante (reembolso pendiente)'),
            ('manual_settlement', 'Liquidación manual confirmada'),
        ],
        compute='_compute_close_type',
        readonly=True,
    )
    confirmation_message = fields.Html(
        compute='_compute_confirmation_message',
        sanitize=False,
        readonly=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de cobro (vuelto)',
        domain="[('type', 'in', ['bank', 'cash'])]",
        check_company=True,
    )

    @api.depends('amount_balance', 'advance_id', 'advance_id.state', 'advance_id.currency_id')
    def _compute_close_type(self):
        for wizard in self:
            advance = wizard.advance_id
            if advance.state == 'pending_settlement':
                wizard.close_type = 'manual_settlement'
                continue
            currency = advance.currency_id
            if currency.is_zero(wizard.amount_balance):
                wizard.close_type = 'balanced'
            elif wizard.amount_balance > 0:
                wizard.close_type = 'surplus'
            else:
                wizard.close_type = 'deficit'

    @api.depends('close_type', 'amount_balance', 'advance_id')
    def _compute_confirmation_message(self):
        for wizard in self:
            advance = wizard.advance_id
            amount = abs(wizard.amount_balance)
            if wizard.close_type == 'balanced':
                wizard.confirmation_message = _(
                    '<p>El anticipo <strong>%(name)s</strong> está cuadrado.</p>'
                    '<p>Anticipo: %(advance)s — Gastado: %(spent)s</p>'
                    '<p>¿Confirma el cierre del anticipo?</p>',
                    name=advance.name,
                    advance=advance.amount,
                    spent=advance.amount_spent,
                )
            elif wizard.close_type == 'surplus':
                wizard.confirmation_message = _(
                    '<p>El empleado <strong>%(employee)s</strong> debe devolver '
                    '<strong>%(amount)s</strong> (vuelto).</p>'
                    '<p>Se registrará el ingreso en caja/banco y se conciliará '
                    'la cuenta de anticipo.</p>'
                    '<p>¿Confirma la liquidación?</p>',
                    employee=advance.employee_id.name,
                    amount=amount,
                )
            elif wizard.close_type == 'manual_settlement':
                wizard.confirmation_message = _(
                    '<p>El anticipo <strong>%(name)s</strong> está pendiente de liquidación.</p>'
                    '<p>Confirme que tesorería ya pagó al empleado y concilió la cuenta '
                    'por pagar del empleado en contabilidad.</p>'
                    '<p>¿Confirma el cierre definitivo del anticipo?</p>',
                    name=advance.name,
                )
            else:
                wizard.confirmation_message = _(
                    '<p>Los gastos superan el anticipo en <strong>%(amount)s</strong>.</p>'
                    '<p>La empresa debe <strong>%(amount)s</strong> al empleado '
                    '<strong>%(employee)s</strong>.</p>'
                    '<p><strong>No</strong> se generará pago bancario automático. '
                    'El saldo quedará en la cuenta del empleado hasta que tesorería '
                    'registre el pago y concilie manualmente.</p>'
                    '<p>¿Confirma pasar el anticipo a pendiente de liquidación?</p>',
                    employee=advance.employee_id.name,
                    amount=amount,
                )

    def _reconcile_advance_account_lines(self, advance, partner):
        advance_lines = self.env['account.move.line'].search([
            ('account_id', '=', advance.account_advance_id.id),
            ('partner_id', '=', partner.id),
            ('reconciled', '=', False),
            ('parent_state', '=', 'posted'),
        ])
        if advance_lines:
            advance_lines.reconcile()

    def action_confirm_close(self):
        self.ensure_one()
        advance = self.advance_id
        partner = advance._get_employee_partner()

        if self.close_type == 'manual_settlement':
            advance.write({'state': 'closed'})
            advance.message_post(body=_(
                'Liquidación manual confirmada. Anticipo cerrado.',
            ))
            return {'type': 'ir.actions.act_window_close'}

        if self.close_type == 'balanced':
            self._reconcile_advance_account_lines(advance, partner)
            advance.write({'state': 'closed'})
            advance.message_post(body=_(
                'Anticipo cerrado. Saldo cuadrado sin diferencia.',
            ))
            return {'type': 'ir.actions.act_window_close'}

        if self.close_type == 'surplus':
            if not self.journal_id or not self.journal_id.default_account_id:
                raise UserError(_(
                    'Seleccione el diario donde el empleado depositará el vuelto.',
                ))
            amount = abs(self.amount_balance)
            move = self.env['account.move'].create({
                'journal_id': self.journal_id.id,
                'date': fields.Date.context_today(self),
                'ref': _('Vuelto anticipo — %s', advance.name),
                'line_ids': [
                    (0, 0, {
                        'account_id': self.journal_id.default_account_id.id,
                        'debit': amount,
                        'credit': 0.0,
                        'name': _('Devolución vuelto — %s', advance.employee_id.name),
                    }),
                    (0, 0, {
                        'account_id': advance.account_advance_id.id,
                        'partner_id': partner.id,
                        'debit': 0.0,
                        'credit': amount,
                        'name': _('Cierre anticipo — %s', advance.employee_id.name),
                    }),
                ],
            })
            move.action_post()
            self._reconcile_advance_account_lines(advance, partner)
            advance.write({
                'closing_move_id': move.id,
                'state': 'closed',
            })
            advance.message_post(body=_(
                'Anticipo cerrado. Vuelto registrado: %(amount)s.',
                amount=amount,
            ))
            return {'type': 'ir.actions.act_window_close'}

        # Faltante: traspasar saldo a cuenta por pagar del empleado, sin pago bancario.
        amount = abs(self.amount_balance)
        payable_account = advance._get_employee_payable_account()
        move = self.env['account.move'].create({
            'journal_id': advance.journal_id.id,
            'date': fields.Date.context_today(self),
            'ref': _('Faltante anticipo — %s', advance.name),
            'line_ids': [
                (0, 0, {
                    'account_id': advance.account_advance_id.id,
                    'partner_id': partner.id,
                    'debit': amount,
                    'credit': 0.0,
                    'name': _('Traspaso faltante anticipo — %s', advance.employee_id.name),
                }),
                (0, 0, {
                    'account_id': payable_account.id,
                    'partner_id': partner.id,
                    'debit': 0.0,
                    'credit': amount,
                    'name': _('Por pagar a empleado — %s', advance.employee_id.name),
                }),
            ],
        })
        move.action_post()
        self._reconcile_advance_account_lines(advance, partner)
        advance.write({
            'closing_move_id': move.id,
            'state': 'pending_settlement',
        })
        advance.message_post(body=_(
            'Anticipo con faltante de %(amount)s. Saldo trasladado a cuenta del '
            'empleado. Pendiente de pago y cuadre manual en tesorería.',
            amount=amount,
        ))
        return {'type': 'ir.actions.act_window_close'}
