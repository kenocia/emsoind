# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class KenociaApplyAdvanceWizard(models.TransientModel):
    _name = 'kenocia.apply.advance.wizard'
    _description = 'Wizard — Aplicar Adelanto a Factura'

    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura',
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        related='invoice_id.partner_id',
        string='Contacto',
    )
    currency_id = fields.Many2one(
        related='invoice_id.currency_id',
    )
    invoice_residual = fields.Monetary(
        related='invoice_id.amount_residual',
        string='Saldo pendiente factura',
    )
    line_ids = fields.One2many(
        comodel_name='kenocia.apply.advance.wizard.line',
        inverse_name='wizard_id',
        string='Adelantos disponibles',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        invoice_id = self.env.context.get('default_invoice_id')
        if invoice_id:
            invoice = self.env['account.move'].browse(invoice_id)
            res['invoice_id'] = invoice.id
            advances = invoice._get_applicable_advances()
            res['line_ids'] = [
                (0, 0, {
                    'advance_id': advance.id,
                    'amount_available': advance.amount_residual,
                    'amount_to_apply': 0.0,
                })
                for advance in advances
            ]
        return res

    def action_apply(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda line: line.amount_to_apply > 0)
        if not lines:
            raise UserError(_('Debe ingresar al menos un monto a aplicar.'))
        total_to_apply = sum(lines.mapped('amount_to_apply'))
        if self.currency_id.compare_amounts(total_to_apply, self.invoice_residual) > 0:
            raise UserError(_(
                'El total a aplicar (%(apply)s) supera el saldo de la factura (%(res)s).',
                apply=self.currency_id.format(total_to_apply),
                res=self.currency_id.format(self.invoice_residual),
            ))
        for line in lines:
            line.advance_id._apply_to_invoice(self.invoice_id, line.amount_to_apply)
        return {'type': 'ir.actions.act_window_close'}


class KenociaApplyAdvanceWizardLine(models.TransientModel):
    _name = 'kenocia.apply.advance.wizard.line'
    _description = 'Línea wizard aplicar adelanto'

    wizard_id = fields.Many2one(
        comodel_name='kenocia.apply.advance.wizard',
        required=True,
        ondelete='cascade',
    )
    advance_id = fields.Many2one(
        comodel_name='kenocia.advance.payment',
        string='Adelanto',
        required=True,
    )
    currency_id = fields.Many2one(
        related='wizard_id.currency_id',
    )
    amount_available = fields.Monetary(
        string='Disponible',
        currency_field='currency_id',
    )
    amount_to_apply = fields.Monetary(
        string='Aplicar',
        currency_field='currency_id',
    )

    @api.constrains('amount_to_apply', 'amount_available')
    def _check_amount_to_apply(self):
        for line in self:
            if line.amount_to_apply < 0:
                raise ValidationError(_('El monto a aplicar no puede ser negativo.'))
            if line.currency_id.compare_amounts(line.amount_to_apply, line.amount_available) > 0:
                raise ValidationError(_(
                    'El monto a aplicar supera el saldo del adelanto.',
                ))
