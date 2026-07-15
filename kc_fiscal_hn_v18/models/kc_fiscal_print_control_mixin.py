# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

SAR_PRINT_LABEL_ORIGINAL = 'ORIGINAL · CLIENTE'
SAR_PRINT_LABEL_COPIA = 'COPIA · EMISOR'

SAR_PRINT_PROTECTED_FIELDS = frozenset({
    'sar_print_count',
    'sar_print_reissue_authorized',
})


class SarPrintControlMixin(models.AbstractModel):
    _name = 'kc_fiscal_hn.print.control.mixin'
    _description = 'Control de impresión SAR (Original / Copia)'

    sar_print_count = fields.Integer(
        string='Impresiones SAR',
        default=0,
        copy=False,
        readonly=True,
    )
    sar_print_reissue_authorized = fields.Boolean(
        string='Reimpresión Original autorizada',
        default=False,
        copy=False,
        readonly=True,
    )
    sar_print_label = fields.Char(
        string='Etiqueta impresión SAR',
        compute='_compute_sar_print_label',
    )
    sar_print_can_authorize_reissue = fields.Boolean(
        compute='_compute_sar_print_reissue_ui',
    )
    sar_print_can_cancel_reissue = fields.Boolean(
        compute='_compute_sar_print_reissue_ui',
    )
    sar_print_reissue_pending_user_id = fields.Many2one(
        'res.users',
        string='Autorizado por',
        compute='_compute_sar_print_reissue_pending',
    )
    sar_print_reissue_pending_date = fields.Datetime(
        string='Fecha autorización pendiente',
        compute='_compute_sar_print_reissue_pending',
    )
    sar_print_reissue_pending_reason = fields.Text(
        string='Motivo autorización pendiente',
        compute='_compute_sar_print_reissue_pending',
    )

    @api.depends('sar_print_count')
    def _compute_sar_print_label(self):
        for record in self:
            record.sar_print_label = record._sar_print_label_for_number(
                record.sar_print_count,
            )

    @api.depends(
        'sar_print_count',
        'sar_print_reissue_authorized',
        'state',
        'move_type',
        'journal_id.document_fiscal',
    )
    def _compute_sar_print_reissue_ui(self):
        for record in self:
            eligible = record._sar_print_is_eligible()
            record.sar_print_can_authorize_reissue = (
                eligible
                and record.sar_print_count > 0
                and not record.sar_print_reissue_authorized
            )
            record.sar_print_can_cancel_reissue = (
                eligible and record.sar_print_reissue_authorized
            )

    @api.depends('sar_print_reissue_authorized')
    def _compute_sar_print_reissue_pending(self):
        ReissueLog = self.env['kc_fiscal_hn.print.reissue.log']
        for record in self:
            record.sar_print_reissue_pending_user_id = False
            record.sar_print_reissue_pending_date = False
            record.sar_print_reissue_pending_reason = False
            if not record.sar_print_reissue_authorized or not record.id:
                continue
            log = ReissueLog.search([
                ('res_model', '=', record._name),
                ('res_id', '=', record.id),
                ('action', '=', 'authorized'),
            ], order='authorized_date desc', limit=1)
            if log:
                record.sar_print_reissue_pending_user_id = log.user_id
                record.sar_print_reissue_pending_date = log.authorized_date
                record.sar_print_reissue_pending_reason = log.reason

    def _sar_print_controlled_move_types(self):
        return ['out_invoice']

    def _sar_print_is_eligible(self):
        self.ensure_one()
        journal = self.journal_id
        if not journal:
            return False
        return (
            self.state == 'posted'
            and self.move_type in self._sar_print_controlled_move_types()
            and journal.document_fiscal == 'client'
        )

    def _check_sar_print_reissue_manager(self):
        if not self.env.user.has_group(
            'kc_fiscal_hn_v18.group_fiscal_sequence_manager'
        ):
            raise AccessError(_(
                'Solo el Administrador de Numeración Fiscal puede gestionar '
                'reautorizaciones de impresión SAR.',
            ))

    def _sar_print_label_for_number(self, print_number):
        if print_number <= 1:
            return SAR_PRINT_LABEL_ORIGINAL
        return SAR_PRINT_LABEL_COPIA

    def _sar_print_prepare_render(self, report):
        """Calcula la etiqueta prospectiva para el render sin persistir."""
        self.ensure_one()
        if not self._sar_print_is_eligible():
            return False
        prospective = self.sar_print_count + 1
        if self.sar_print_reissue_authorized:
            return {
                'res_model': self._name,
                'res_id': self.id,
                'label': SAR_PRINT_LABEL_ORIGINAL,
                'prospective_number': prospective,
                'print_type': 'original_reautorizado',
                'report_id': report.id,
                'clear_reissue': True,
            }
        print_type = 'original' if prospective == 1 else 'copia'
        return {
            'res_model': self._name,
            'res_id': self.id,
            'label': self._sar_print_label_for_number(prospective),
            'prospective_number': prospective,
            'print_type': print_type,
            'report_id': report.id,
            'clear_reissue': False,
        }

    def _register_sar_print(
        self, report, prospective_number, print_type, clear_reissue=False,
    ):
        self.ensure_one()
        write_vals = {'sar_print_count': prospective_number}
        if clear_reissue:
            write_vals['sar_print_reissue_authorized'] = False
        self.with_context(sar_print_internal=True).write(write_vals)
        self.env['kc_fiscal_hn.print.log'].sudo().create({
            'res_model': self._name,
            'res_id': self.id,
            'document_name': self.display_name,
            'document_number': self.name,
            'move_type': self.move_type,
            'company_id': self.company_id.id,
            'print_number': prospective_number,
            'print_type': print_type,
            'report_id': report.id,
            'user_id': self.env.user.id,
        })
        _logger.info(
            'SAR_PRINT move=%s user=%s type=%s number=%s report=%s reissue=%s',
            self.id,
            self.env.user.login,
            print_type,
            prospective_number,
            report.report_name,
            clear_reissue,
        )

    def _sar_print_authorize_reissue(self, reason):
        self.ensure_one()
        self._check_sar_print_reissue_manager()
        if not self._sar_print_is_eligible():
            raise UserError(_(
                'Este documento no es elegible para reautorización de '
                'impresión SAR.',
            ))
        if self.sar_print_count <= 0:
            raise UserError(_(
                'La reautorización solo aplica a documentos ya impresos '
                'al menos una vez.',
            ))
        if self.sar_print_reissue_authorized:
            raise UserError(_(
                'Ya existe una reautorización pendiente para este documento.',
            ))
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_('Debe indicar el motivo de la reautorización.'))
        self.with_context(sar_print_internal=True).write({
            'sar_print_reissue_authorized': True,
        })
        self.env['kc_fiscal_hn.print.reissue.log'].sudo().create({
            'res_model': self._name,
            'res_id': self.id,
            'document_name': self.display_name,
            'action': 'authorized',
            'reason': reason,
            'user_id': self.env.user.id,
            'print_count_at_authorization': self.sar_print_count,
        })

    def _sar_print_cancel_reissue(self, reason):
        self.ensure_one()
        self._check_sar_print_reissue_manager()
        if not self._sar_print_is_eligible():
            raise UserError(_(
                'Este documento no es elegible para cancelar la '
                'reautorización de impresión SAR.',
            ))
        if not self.sar_print_reissue_authorized:
            raise UserError(_(
                'No hay una reautorización pendiente que cancelar.',
            ))
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_('Debe indicar el motivo de la cancelación.'))
        print_count = self.sar_print_count
        self.with_context(sar_print_internal=True).write({
            'sar_print_reissue_authorized': False,
        })
        self.env['kc_fiscal_hn.print.reissue.log'].sudo().create({
            'res_model': self._name,
            'res_id': self.id,
            'document_name': self.display_name,
            'action': 'cancelled',
            'reason': reason,
            'user_id': self.env.user.id,
            'print_count_at_authorization': print_count,
        })

    def write(self, vals):
        if (
            SAR_PRINT_PROTECTED_FIELDS & set(vals.keys())
            and not self.env.context.get('sar_print_internal')
        ):
            raise UserError(_(
                'Los campos de control de impresión SAR no pueden '
                'modificarse manualmente.',
            ))
        return super().write(vals)

    def action_view_sar_print_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Impresiones SAR'),
            'res_model': 'kc_fiscal_hn.print.log',
            'view_mode': 'list',
            'domain': [
                ('res_model', '=', self._name),
                ('res_id', '=', self.id),
            ],
            'context': {
                'create': False,
                'edit': False,
                'delete': False,
            },
        }

    def action_view_sar_print_reissue_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reautorizaciones SAR'),
            'res_model': 'kc_fiscal_hn.print.reissue.log',
            'view_mode': 'list',
            'domain': [
                ('res_model', '=', self._name),
                ('res_id', '=', self.id),
            ],
            'context': {
                'create': False,
                'edit': False,
                'delete': False,
            },
        }

    def action_open_sar_print_reissue_wizard(self):
        self.ensure_one()
        self._check_sar_print_reissue_manager()
        if not self.sar_print_can_authorize_reissue:
            raise UserError(_(
                'Este documento no cumple las condiciones para autorizar '
                'reimpresión como Original.',
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Autorizar reimpresión como Original'),
            'res_model': 'kc_fiscal_hn.print.reissue.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
            },
        }

    def action_open_sar_print_reissue_cancel_wizard(self):
        self.ensure_one()
        self._check_sar_print_reissue_manager()
        if not self.sar_print_can_cancel_reissue:
            raise UserError(_(
                'No hay una reautorización pendiente que cancelar.',
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cancelar reautorización pendiente'),
            'res_model': 'kc_fiscal_hn.print.reissue.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
            },
        }
