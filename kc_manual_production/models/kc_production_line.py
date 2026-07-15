# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class KcProductionLine(models.Model):
    """Línea de Producción: operadores, categorías y filtro de RP."""
    _name = 'kc.production.line'
    _description = 'Línea de Producción'
    _order = 'sequence, name, id'

    name = fields.Char(
        string='Nombre',
        required=True,
        translate=True,
    )
    code = fields.Char(
        string='Código',
        help='Código corto opcional para identificar la línea.',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    user_ids = fields.Many2many(
        comodel_name='res.users',
        relation='kc_production_line_user_rel',
        column1='line_id',
        column2='user_id',
        string='Operadores asignados',
        help='Usuarios que trabajan en esta línea. Los Operadores de Producción '
             'solo ven los RP de sus líneas; los Operadores de Bodega filtran '
             'los RP disponibles al crear un CMP.',
    )
    product_categ_ids = fields.Many2many(
        comodel_name='product.category',
        relation='kc_production_line_product_categ_rel',
        column1='line_id',
        column2='categ_id',
        string='Categorías de producto',
        help='Productos cuya categoría (o subcategoría) pertenece a alguna de '
             'estas categorías se asignan a esta línea de producción.',
    )
    team_id = fields.Many2one(
        comodel_name='crm.team',
        string='Equipo de Venta',
        help='Informativo / reporting. No afecta la resolución de productos '
             'ni los dominios de RP.',
    )
    work_center_ids = fields.One2many(
        comodel_name='kc.work.center',
        inverse_name='production_line_id',
        string='Centros de Trabajo',
    )
    work_center_count = fields.Integer(
        string='N° Centros',
        compute='_compute_work_center_count',
    )
    entry_count = fields.Integer(
        string='N° Registros de Producción',
        compute='_compute_entry_count',
    )

    _sql_constraints = [
        (
            'kc_production_line_name_company_uniq',
            'unique(name, company_id)',
            'Ya existe una línea de producción con ese nombre en la compañía.',
        ),
    ]

    @api.depends('work_center_ids')
    def _compute_work_center_count(self):
        for rec in self:
            rec.work_center_count = len(rec.work_center_ids)

    @api.depends('name')
    def _compute_entry_count(self):
        Entry = self.env['kc.production.entry']
        if not self.ids:
            for rec in self:
                rec.entry_count = 0
            return
        grouped = Entry.read_group(
            domain=[('production_line_id', 'in', self.ids)],
            fields=['production_line_id'],
            groupby=['production_line_id'],
        )
        counts = {
            row['production_line_id'][0]: row['production_line_id_count']
            for row in grouped
            if row.get('production_line_id')
        }
        for rec in self:
            rec.entry_count = counts.get(rec.id, 0)

    def action_view_work_centers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Centros de Trabajo'),
            'res_model': 'kc.work.center',
            'view_mode': 'list,form',
            'domain': [('production_line_id', '=', self.id)],
            'context': {'default_production_line_id': self.id},
        }

    @api.constrains('user_ids', 'company_id')
    def _check_users_company(self):
        for rec in self:
            invalid = rec.user_ids.filtered(
                lambda u: rec.company_id not in u.company_ids)
            if invalid:
                raise ValidationError(_(
                    'Los usuarios %(users)s no pertenecen a la compañía %(company)s.',
                    users=', '.join(invalid.mapped('name')),
                    company=rec.company_id.name,
                ))

    @api.constrains('product_categ_ids', 'company_id')
    def _check_product_categ_overlap(self):
        """Una categoría no puede pertenecer a dos líneas de la misma compañía."""
        for rec in self:
            if not rec.product_categ_ids:
                continue
            others = self.search([
                ('id', '!=', rec.id),
                ('company_id', '=', rec.company_id.id),
                ('active', '=', True),
            ])
            for categ in rec.product_categ_ids:
                conflict = others.filtered(lambda l: categ in l.product_categ_ids)
                if conflict:
                    raise ValidationError(_(
                        'La categoría "%(categ)s" ya está asignada a la línea '
                        '"%(line)s". Una categoría solo puede pertenecer a una '
                        'línea de producción por compañía.',
                        categ=categ.complete_name,
                        line=conflict[0].name,
                    ))

    @api.model
    def _kc_categ_depth(self, category):
        if not category or not category.parent_path:
            return 0
        return category.parent_path.count('/') + 1

    @api.model
    def _kc_product_matches_categ(self, product_categ, allowed_categ):
        """True si la categoría del producto es la permitida o una hija."""
        if not product_categ or not allowed_categ:
            return False
        if product_categ.id == allowed_categ.id:
            return True
        return product_categ.parent_path.startswith(allowed_categ.parent_path)

    @api.model
    def resolve_for_product(self, product, company=None):
        """Devuelve la línea de producción que corresponde al producto.

        Si varias líneas coinciden, gana la categoría configurada más específica
        (mayor profundidad en el árbol de categorías).
        """
        if not product:
            return self.browse()
        company = company or self.env.company
        product_categ = product.categ_id
        lines = self.search([
            ('company_id', '=', company.id),
            ('active', '=', True),
        ])
        best_line = self.browse()
        best_depth = -1
        for line in lines:
            for allowed in line.product_categ_ids:
                if not self._kc_product_matches_categ(product_categ, allowed):
                    continue
                depth = self._kc_categ_depth(allowed)
                if depth > best_depth:
                    best_depth = depth
                    best_line = line
        return best_line

    def action_view_entries(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registros de Producción'),
            'res_model': 'kc.production.entry',
            'view_mode': 'list,form',
            'domain': [('production_line_id', '=', self.id)],
            'context': {'default_production_line_id': self.id},
        }
