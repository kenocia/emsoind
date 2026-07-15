# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CustomTechnicalAttribute(models.Model):
    _name = 'custom.technical.attribute'
    _description = 'Atributo Técnico'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    display_type = fields.Selection(
        selection=[
            ('selection', 'Selección'),
            ('radio', 'Radio'),
            ('numeric', 'Numérico'),
            ('text', 'Texto'),
        ],
        required=True,
        default='selection',
    )
    uom_id = fields.Many2one('uom.uom', string='Unidad de medida')
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    value_ids = fields.One2many(
        'custom.technical.attribute.value',
        'attribute_id',
        string='Valores',
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'El código del atributo debe ser único.'),
    ]

    @api.constrains('code')
    def _check_code(self):
        for rec in self:
            if not rec.code or not rec.code.strip():
                raise ValidationError('El código del atributo es obligatorio.')
            if ' ' in rec.code:
                raise ValidationError('El código no debe contener espacios.')


class CustomTechnicalAttributeValue(models.Model):
    _name = 'custom.technical.attribute.value'
    _description = 'Valor de Atributo Técnico'
    _order = 'sequence, name'

    attribute_id = fields.Many2one(
        'custom.technical.attribute',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.constrains('attribute_id', 'name')
    def _check_name(self):
        for rec in self:
            if not rec.name or not rec.name.strip():
                raise ValidationError('El nombre del valor es obligatorio.')

    @api.ondelete(at_uninstall=False)
    def _unlink_except_used(self):
        """Impide eliminar un valor en uso. La trazabilidad (lotes), las ventas
        y las listas de precios dependen de la clave técnica/de configuración
        derivada de este valor; las listas de precios quedan protegidas de forma
        transitiva al bloquear las configuraciones que lo usan."""
        ConfigValue = self.env['custom.product.technical.configuration.value']
        SaleValue = self.env['custom.sale.order.line.technical.value']
        LotValue = self.env['custom.stock.lot.technical.value']
        AttrLine = self.env['custom.product.technical.attribute.line']
        for value in self:
            usages = []
            configs = ConfigValue.search(
                [('value_id', '=', value.id)]
            ).mapped('configuration_id')
            if configs:
                usages.append(
                    _('configuraciones de producto: %s')
                    % ', '.join(configs.mapped('display_name'))
                )
            if SaleValue.search_count([('value_id', '=', value.id)]):
                usages.append(_('líneas de pedidos de venta'))
            if LotValue.search_count([('value_id', '=', value.id)]):
                usages.append(_('lotes de inventario'))
            attr_lines = AttrLine.search([
                '|',
                ('allowed_value_ids', '=', value.id),
                ('default_value_id', '=', value.id),
            ])
            if attr_lines:
                usages.append(
                    _('atributos por producto: %s')
                    % ', '.join(attr_lines.mapped('product_tmpl_id.display_name'))
                )
            if usages:
                raise UserError(_(
                    'No se puede eliminar el valor "%(value)s" porque está en uso en:\n'
                    '- %(usages)s\n\n'
                    'Las listas de precios y la trazabilidad dependen de la clave '
                    'técnica/de configuración derivada de este valor. Desactívelo '
                    '(archivar) en lugar de eliminarlo.'
                ) % {'value': value.display_name, 'usages': '\n- '.join(usages)})


class CustomProductTechnicalAttributeLine(models.Model):
    _name = 'custom.product.technical.attribute.line'
    _description = 'Atributo técnico por producto'
    _order = 'sequence, id'

    product_tmpl_id = fields.Many2one(
        'product.template',
        required=True,
        ondelete='cascade',
        index=True,
    )
    attribute_id = fields.Many2one(
        'custom.technical.attribute',
        required=True,
        ondelete='restrict',
    )
    required = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    allowed_value_ids = fields.Many2many(
        'custom.technical.attribute.value',
        relation='kc_prod_tech_attr_line_value_rel',
        column1='line_id',
        column2='value_id',
        string='Valores permitidos',
        domain="[('attribute_id', '=', attribute_id)]",
    )
    default_value_id = fields.Many2one(
        'custom.technical.attribute.value',
        string='Valor por defecto',
        domain="[('attribute_id', '=', attribute_id)]",
    )

    @api.constrains('default_value_id', 'allowed_value_ids')
    def _check_default_in_allowed(self):
        for line in self:
            if line.default_value_id and line.allowed_value_ids:
                if line.default_value_id not in line.allowed_value_ids:
                    raise ValidationError(
                        'El valor por defecto debe estar entre los valores permitidos.'
                    )


class CustomSaleOrderLineTechnicalValue(models.Model):
    _name = 'custom.sale.order.line.technical.value'
    _description = 'Valor técnico en línea de venta'
    _inherit = 'custom.technical.value.mixin'
    _order = 'sequence, id'

    sale_order_line_id = fields.Many2one(
        'sale.order.line',
        required=True,
        ondelete='cascade',
        index=True,
    )
    attribute_id = fields.Many2one(
        'custom.technical.attribute',
        required=True,
        ondelete='restrict',
    )
    display_type = fields.Selection(
        related='attribute_id.display_type',
        store=True,
        readonly=True,
    )
    value_text = fields.Char()
    value_number = fields.Float()
    value_id = fields.Many2one(
        'custom.technical.attribute.value',
        domain="[('attribute_id', '=', attribute_id)]",
    )
    uom_id = fields.Many2one('uom.uom')
    sequence = fields.Integer(default=10)
    required = fields.Boolean(default=False)

    @api.onchange('value_id')
    def _onchange_value_id(self):
        for rec in self:
            if rec.value_id and rec.attribute_id.display_type in ('selection', 'radio'):
                rec.value_text = False
                rec.value_number = 0.0

    @api.onchange('attribute_id')
    def _onchange_attribute_id(self):
        for rec in self:
            if rec.attribute_id:
                rec.uom_id = rec.attribute_id.uom_id
                rec.value_id = False
                rec.value_text = False
                rec.value_number = 0.0


class CustomStockLotTechnicalValue(models.Model):
    _name = 'custom.stock.lot.technical.value'
    _description = 'Valor técnico en lote'
    _inherit = 'custom.technical.value.mixin'
    _order = 'sequence, id'

    lot_id = fields.Many2one(
        'stock.lot',
        required=True,
        ondelete='cascade',
        index=True,
    )
    attribute_id = fields.Many2one(
        'custom.technical.attribute',
        required=True,
        ondelete='restrict',
    )
    display_type = fields.Selection(
        related='attribute_id.display_type',
        store=True,
        readonly=True,
    )
    value_text = fields.Char()
    value_number = fields.Float()
    value_id = fields.Many2one(
        'custom.technical.attribute.value',
        domain="[('attribute_id', '=', attribute_id)]",
    )
    uom_id = fields.Many2one('uom.uom')
    sequence = fields.Integer(default=10)
