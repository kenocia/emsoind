# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class KcFiscalPrintReissueLog(models.Model):
    _name = 'kc_fiscal_hn.print.reissue.log'
    _description = 'Auditoría de reautorización de impresión SAR'
    _order = 'authorized_date desc'
    _rec_name = 'document_name'

    res_model = fields.Char(string='Modelo', required=True, index=True)
    res_id = fields.Integer(string='ID registro', required=True, index=True)
    document_name = fields.Char(string='Documento')
    action = fields.Selection([
        ('authorized', 'Autorizada'),
        ('cancelled', 'Cancelada'),
    ], string='Acción', required=True, index=True)
    reason = fields.Text(string='Motivo', required=True)
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        required=True,
        default=lambda self: self.env.user,
    )
    authorized_date = fields.Datetime(
        string='Fecha / hora',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    print_count_at_authorization = fields.Integer(
        string='Impresiones al momento',
        required=True,
    )

    def init(self):
        super().init()
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS kc_fiscal_hn_print_reissue_log_res_date_idx
            ON kc_fiscal_hn_print_reissue_log (res_model, res_id, authorized_date DESC)
        """)

    def write(self, vals):
        if not self.env.context.get('sar_print_internal'):
            raise UserError(_(
                'El registro de auditoría de reautorización SAR no puede '
                'modificarse.',
            ))
        return super().write(vals)

    def unlink(self):
        raise UserError(_(
            'El registro de auditoría de reautorización SAR no puede eliminarse.',
        ))
