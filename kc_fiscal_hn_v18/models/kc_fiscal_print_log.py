# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class KcFiscalPrintLog(models.Model):
    _name = 'kc_fiscal_hn.print.log'
    _description = 'Auditoría de impresiones SAR'
    _order = 'print_date desc'
    _rec_name = 'document_name'

    res_model = fields.Char(string='Modelo', required=True, index=True)
    res_id = fields.Integer(string='ID registro', required=True, index=True)
    document_name = fields.Char(string='Documento')
    document_number = fields.Char(string='Número fiscal')
    move_type = fields.Char(string='Tipo de movimiento')
    company_id = fields.Many2one('res.company', string='Compañía', index=True)
    print_number = fields.Integer(string='N° impresión', required=True)
    print_type = fields.Selection([
        ('original', 'Original'),
        ('copia', 'Copia'),
        ('original_reautorizado', 'Original reautorizado'),
    ], string='Tipo impresión', required=True)
    report_id = fields.Many2one('ir.actions.report', string='Reporte', ondelete='set null')
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        required=True,
        default=lambda self: self.env.user,
    )
    print_date = fields.Datetime(
        string='Fecha / hora',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )

    def init(self):
        super().init()
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS kc_fiscal_hn_print_log_res_date_idx
            ON kc_fiscal_hn_print_log (res_model, res_id, print_date DESC)
        """)

    @api.model
    def _register_hook(self):
        super()._register_hook()
        from odoo.addons.kc_fiscal_hn_v18.hooks import migrate_sar_print_count
        migrate_sar_print_count(self.env)

    def write(self, vals):
        if not self.env.context.get('sar_print_internal'):
            raise UserError(_(
                'El registro de auditoría de impresiones SAR no puede '
                'modificarse.',
            ))
        return super().write(vals)

    def unlink(self):
        raise UserError(_(
            'El registro de auditoría de impresiones SAR no puede eliminarse.',
        ))
