# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductCategory(models.Model):
    _inherit = 'product.category'

    cumple_requisitos_tecnicos = fields.Boolean(
        string="Cumple Requisitos Técnicos",
        compute="_compute_validacion_contable",
        store=False,
        search="_search_cumple_requisitos_tecnicos",
        help="Verifica para la compañía actual que la categoría tiene "
             "las cuentas/diario/método de costeo mínimos que Odoo no "
             "exige por sí solo.",
    )
    validado_contable = fields.Boolean(
        string="Validado por Contabilidad",
        company_dependent=True,
        copy=False,
        tracking=True,
        groups="account.group_account_manager",
        help="Validación humana del responsable contable, "
             "independiente por compañía.",
    )
    estado_validacion_contable = fields.Selection(
        selection=[
            ('no_valida', '🔴 No válida'),
            ('pendiente', '🟡 Pendiente'),
            ('ok', '✅ Validada'),
        ],
        string="Estado Validación Contable",
        compute="_compute_validacion_contable",
        store=False,
        search="_search_estado_validacion_contable",
    )

    @api.depends(
        'property_valuation',
        'property_cost_method',
        'property_account_income_categ_id',
        'property_account_expense_categ_id',
        'property_stock_journal',
        'validado_contable',
    )
    def _compute_validacion_contable(self) -> None:
        # Los campos property_* son company_dependent: al leerlos, el ORM
        # resuelve automáticamente el valor de self.env.company (incluido el
        # fallback de ir.default). Por eso el compute es store=False y queda
        # correcto incluso en escenarios multicompañía.
        for categoria in self:
            # validado_contable está restringido a Contabilidad; sudo() permite
            # calcular el estado para validaciones de negocio (OV, facturas)
            # sin exponer el campo en formularios de otros perfiles.
            validado_contable = categoria.sudo().validado_contable
            cumple = bool(
                categoria.property_account_income_categ_id
                and categoria.property_account_expense_categ_id
                and categoria.property_cost_method
            )
            if categoria.property_valuation == 'real_time':
                # Las cuentas valuation/input/output ya están garantizadas por
                # el constraint nativo de Odoo (_check_valuation_accounts) si la
                # categoría se guardó sin error. Solo añadimos lo que Odoo NO
                # valida por sí mismo: el diario de stock.
                cumple = cumple and bool(categoria.property_stock_journal)
            categoria.cumple_requisitos_tecnicos = cumple
            if not cumple:
                # Si no cumple, el estado es 'no_valida' aunque validado_contable
                # esté en True (auto-neutralización sin reset físico del JSONB).
                categoria.estado_validacion_contable = 'no_valida'
            elif validado_contable:
                categoria.estado_validacion_contable = 'ok'
            else:
                categoria.estado_validacion_contable = 'pendiente'

    def _search_estado_validacion_contable(self, operator, value):
        todas = self.search([])
        if operator in ('=', 'in'):
            ids = [
                c.id for c in todas
                if c.estado_validacion_contable == value
            ]
        else:
            ids = [
                c.id for c in todas
                if c.estado_validacion_contable != value
            ]
        return [('id', 'in', ids)]

    def _search_cumple_requisitos_tecnicos(self, operator, value):
        todas = self.search([])
        ids = [
            c.id for c in todas
            if c.cumple_requisitos_tecnicos == bool(value)
        ]
        return [('id', 'in', ids)]

    @api.constrains('validado_contable')
    def _check_validado_requiere_cumplimiento(self) -> None:
        for categoria in self:
            if (categoria.validado_contable
                    and not categoria.cumple_requisitos_tecnicos):
                raise ValidationError(_(
                    "No se puede marcar como 'Validado por Contabilidad' "
                    "la categoría '%(cat)s' porque no cumple los requisitos "
                    "técnicos contables para la compañía actual.",
                    cat=categoria.display_name,
                ))
