# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    kc_production_line_ids = fields.Many2many(
        comodel_name='kc.production.line',
        relation='kc_production_line_user_rel',
        column1='user_id',
        column2='line_id',
        string='Líneas de Producción',
        help='Líneas de producción a las que está asignado este usuario.',
    )
