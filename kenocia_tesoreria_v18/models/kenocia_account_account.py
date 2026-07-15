# -*- coding: utf-8 -*-
# Copyright 2026 KENOCIA · License LGPL-3

from odoo import _, api, fields, models
from odoo.tools.safe_eval import safe_eval


class AccountAccount(models.Model):
    _inherit = 'account.account'

    kenocia_tesoreria_role = fields.Char(
        string='Rol en tesorería',
        compute='_compute_kenocia_tesoreria_role',
    )

    @api.model
    def _kenocia_prepare_chart_action(self, name, domain, search_defaults=None):
        action = self.env['ir.actions.actions']._for_xml_id(
            'account.action_account_form',
        )
        action_context = action.get('context') or {}
        if isinstance(action_context, str):
            action_context = safe_eval(action_context)
        if search_defaults:
            action_context.update(search_defaults)
        action.update({
            'name': name,
            'domain': domain,
            'context': action_context,
        })
        return action

    @api.model
    def action_kenocia_open_bank_cash_accounts(self):
        return self._kenocia_prepare_chart_action(
            _('Cuentas banco y efectivo'),
            [('account_type', '=', 'asset_cash')],
            {'search_default_kenocia_bank_cash': 1},
        )

    @api.model
    def action_kenocia_open_advance_accounts(self):
        return self._kenocia_prepare_chart_action(
            _('Cuentas de anticipo'),
            [
                ('account_type', 'in', (
                    'asset_current',
                    'asset_receivable',
                    'asset_prepayments',
                )),
            ],
            {'search_default_kenocia_advance_accounts': 1},
        )

    @api.depends('company_ids')
    def _compute_kenocia_tesoreria_role(self):
        companies = self.env['res.company'].search([])
        roles = {}
        for company in companies:
            if company.kenocia_advance_account_cxc_id:
                roles[company.kenocia_advance_account_cxc_id.id] = _(
                    'Anticipo clientes (CXC)',
                )
            if company.kenocia_advance_account_cxp_id:
                roles[company.kenocia_advance_account_cxp_id.id] = _(
                    'Anticipo proveedores (CXP)',
                )
        for account in self:
            account.kenocia_tesoreria_role = roles.get(account.id, '')
