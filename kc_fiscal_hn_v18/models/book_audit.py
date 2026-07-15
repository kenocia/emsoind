# -*- coding: utf-8 -*-

from odoo import api, fields, models


class FiscalBookAudit(models.Model):
    """Historial de cambios en líneas de libros fiscales SAR."""

    _name = 'kc_fiscal_hn.book.audit'
    _description = 'Auditoría Libros Fiscales SAR'
    _order = 'create_date desc'

    res_model = fields.Char(string='Modelo', required=True, index=True)
    res_id = fields.Integer(string='ID registro', required=True, index=True)
    field_name = fields.Char(string='Campo', required=True)
    old_value = fields.Text(string='Valor anterior')
    new_value = fields.Text(string='Valor nuevo')
    action = fields.Selection([
        ('generacion', 'Generación'),
        ('modificacion', 'Modificación'),
        ('declaracion', 'Declaración'),
        ('rectificacion', 'Rectificación'),
    ], string='Acción', required=True, default='modificacion')
    reason = fields.Text(string='Motivo / notas')
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        required=True,
        default=lambda self: self.env.user,
    )
    create_date = fields.Datetime(
        string='Fecha',
        default=fields.Datetime.now,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )
    book_line_display = fields.Char(
        string='Línea',
        compute='_compute_book_line_display',
    )

    @api.depends('res_model', 'res_id')
    def _compute_book_line_display(self) -> None:
        for audit in self:
            if audit.res_model and audit.res_id:
                try:
                    rec = self.env[audit.res_model].browse(audit.res_id)
                    audit.book_line_display = rec.display_name if rec.exists() else f'{audit.res_model},{audit.res_id}'
                except Exception:
                    audit.book_line_display = f'{audit.res_model},{audit.res_id}'
            else:
                audit.book_line_display = ''

    @api.depends('res_model', 'res_id', 'field_name', 'create_date')
    def _compute_display_name(self) -> None:
        for audit in self:
            audit.display_name = f'{audit.book_line_display or audit.res_model} — {audit.field_name}'
