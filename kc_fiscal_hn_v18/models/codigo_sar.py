# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CodigoSAR(models.Model):
    _name = 'kc_fiscal_hn.codigo.sar'
    _description = 'Códigos SAR Honduras — Impuestos'
    _order = 'codigo asc'

    codigo = fields.Char(
        string='Código SAR',
        required=True,
        help='Código oficial del SAR Honduras '
             'para el tipo de impuesto.',
    )
    nombre = fields.Char(
        string='Nombre',
        required=True,
    )
    tipo_impuesto = fields.Selection([
        ('isv', 'ISV'),
        ('retencion', 'Retención'),
        ('exento', 'Exento'),
        ('exonerado', 'Exonerado'),
        ('otros', 'Otros'),
    ], string='Tipo de Impuesto',
       required=True,
    )
    tipo_uso = fields.Selection([
        ('sale', 'Ventas'),
        ('purchase', 'Compras'),
        ('all', 'Ventas y Compras'),
    ], string='Uso',
       required=True,
       default='all',
    )
    porcentaje = fields.Float(
        string='Porcentaje (%)',
        digits=(5, 2),
    )
    descripcion = fields.Text(
        string='Descripción',
        help='Descripción del código según '
             'normativa SAR Honduras.',
    )
    activo = fields.Boolean(
        string='Activo',
        default=True,
    )
    base_legal = fields.Char(
        string='Base Legal',
        help='Decreto o acuerdo SAR que '
             'define este código.',
    )
    tax_ids = fields.One2many(
        'account.tax',
        'codigo_sar_id',
        string='Impuestos',
    )
    tax_count = fields.Integer(
        string='N° Impuestos',
        compute='_compute_tax_count',
    )

    _sql_constraints = [
        ('codigo_unique',
         'UNIQUE(codigo)',
         'El código SAR debe ser único.'),
    ]

    @api.depends('tax_ids')
    def _compute_tax_count(self):
        for rec in self:
            rec.tax_count = len(rec.tax_ids)

    @api.depends('codigo', 'nombre')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'{rec.codigo} — {rec.nombre}'
