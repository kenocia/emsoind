# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class KcSaleLineSpecsWizard(models.TransientModel):
    _name = 'kc.sale.line.specs.wizard'
    _description = 'Configurar especificaciones técnicas de línea'

    sale_order_id = fields.Many2one('sale.order', required=True, ondelete='cascade')
    sale_order_line_id = fields.Many2one('sale.order.line', ondelete='cascade')
    product_id = fields.Many2one('product.product', required=True)
    product_uom_qty = fields.Float(string='Cantidad', default=1.0, required=True)
    technical_value_ids = fields.One2many(
        'kc.sale.line.specs.wizard.value',
        'wizard_id',
        string='Especificaciones',
    )
    technical_description = fields.Text(compute='_compute_technical_meta', store=False)
    technical_key = fields.Char(compute='_compute_technical_meta', store=False)
    compatible_qty_total = fields.Float(compute='_compute_compatible_info')
    stock_status_message = fields.Char(compute='_compute_compatible_info')
    order_locked = fields.Boolean(compute='_compute_order_locked')

    @api.depends('sale_order_id.state')
    def _compute_order_locked(self):
        for wiz in self:
            wiz.order_locked = wiz.sale_order_id.state not in ('draft', 'sent')

    @api.depends('technical_value_ids', 'technical_value_ids.value_id',
                 'technical_value_ids.value_text', 'technical_value_ids.value_number',
                 'technical_value_ids.attribute_id', 'technical_value_ids.uom_id')
    def _compute_technical_meta(self):
        mixin = self.env['custom.technical.value.mixin']
        for wiz in self:
            wiz.technical_description = mixin.build_technical_description(
                wiz.technical_value_ids
            )
            wiz.technical_key = mixin.build_technical_key(wiz.technical_value_ids)

    @api.depends('technical_key', 'product_id')
    def _compute_compatible_info(self):
        for wiz in self:
            qty = wiz._get_compatible_stock_qty()
            wiz.compatible_qty_total = qty
            if wiz.technical_key:
                if qty > 0:
                    wiz.stock_status_message = _(
                        'Stock estimado para esta medida: %(qty)s unidad(es). '
                        'El lote se asignará en producción o al despachar.'
                    ) % {'qty': qty}
                else:
                    wiz.stock_status_message = _(
                        'Sin stock estimado para esta medida. '
                        'La producción definirá el lote.'
                    )
            else:
                wiz.stock_status_message = _('Complete las características del producto.')

    def action_refresh_compatible_stock(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        line_id = res.get('sale_order_line_id') or self.env.context.get('default_sale_order_line_id')
        product_id = res.get('product_id') or self.env.context.get('default_product_id')
        order_id = res.get('sale_order_id') or self.env.context.get('default_sale_order_id')

        if line_id:
            line = self.env['sale.order.line'].browse(line_id)
            if line.exists():
                res.setdefault('sale_order_id', line.order_id.id)
                res.setdefault('product_id', line.product_id.id)
                res.setdefault('product_uom_qty', line.product_uom_qty)
                tech_commands = self._prepare_values_from_sale_line(line)
                if not tech_commands and line.product_id:
                    tech_commands = self._prepare_values_from_product(line.product_id)
                res['technical_value_ids'] = tech_commands
        if not res.get('technical_value_ids'):
            pid = res.get('product_id') or product_id
            if pid:
                product = self.env['product.product'].browse(pid)
                if product.exists():
                    res.setdefault('product_id', product.id)
                    res['technical_value_ids'] = self._prepare_values_from_product(product)
        if order_id:
            res.setdefault('sale_order_id', order_id)
        return res

    @api.model
    def _prepare_values_from_product(self, product):
        lines = []
        tmpl = product.product_tmpl_id
        for attr_line in tmpl.technical_attribute_line_ids.sorted('sequence'):
            attr = attr_line.attribute_id
            vals = {
                'attribute_id': attr.id,
                'sequence': attr_line.sequence,
                'required': attr_line.required,
                'uom_id': attr.uom_id.id,
            }
            default = attr_line.default_value_id
            if default and attr.display_type in ('selection', 'radio'):
                if not attr_line.allowed_value_ids or default in attr_line.allowed_value_ids:
                    vals['value_id'] = default.id
            elif default and attr.display_type == 'text':
                vals['value_text'] = default.name
            lines.append((0, 0, vals))
        return lines

    @api.model
    def _prepare_values_from_sale_line(self, line):
        lines = []
        for tv in line.technical_value_ids.sorted('sequence'):
            lines.append((0, 0, {
                'attribute_id': tv.attribute_id.id,
                'sequence': tv.sequence,
                'required': tv.required,
                'uom_id': tv.uom_id.id,
                'value_id': tv.value_id.id,
                'value_text': tv.value_text,
                'value_number': tv.value_number,
            }))
        return lines

    def _get_compatible_stock_qty(self):
        self.ensure_one()
        if not self.product_id or not self.technical_key:
            return 0.0
        Quant = self.env['stock.quant']
        quants = Quant.search([
            ('product_id', '=', self.product_id.id),
            ('lot_id', '!=', False),
            ('lot_id.technical_key', '=', self.technical_key),
            ('quantity', '>', 0),
            ('location_id.usage', '=', 'internal'),
        ])
        return sum(quants.mapped('available_quantity'))

    def _validate_specs(self):
        self.ensure_one()
        if not self.product_id.product_tmpl_id.technical_attribute_line_ids:
            raise UserError(_('El producto no tiene atributos técnicos configurados.'))
        if self.product_uom_qty <= 0:
            raise UserError(_('La cantidad debe ser mayor que cero.'))
        missing = []
        for tv in self.technical_value_ids.filtered('required'):
            if tv.display_type == 'numeric' and not tv.value_number:
                missing.append(tv.attribute_id.name)
            elif tv.display_type in ('selection', 'radio') and not tv.value_id:
                missing.append(tv.attribute_id.name)
            elif tv.display_type == 'text' and not (tv.value_text or '').strip():
                missing.append(tv.attribute_id.name)
        if missing:
            raise ValidationError(
                _('Complete: %s') % ', '.join(missing)
            )
        if not self.technical_key:
            raise ValidationError(_('Defina al menos un valor técnico válido.'))
        self._validate_allowed_values()
        self._validate_combination_in_matrix()

    def _validate_combination_in_matrix(self):
        self.ensure_one()
        exists = self.env['product.technical.configuration'].matrix_combination_exists(
            self.product_id, self.technical_value_ids,
        )
        if exists is False:
            raise ValidationError(_(
                'La combinación %(desc)s, no está dada de alta como '
                'configuración técnica del producto "%(product)s" y, por lo '
                'tanto, no puede producirse ni venderse.\n\n'
                'Seleccione una combinación válida o solicite que se agregue a '
                'la matriz de configuraciones del producto.'
            ) % {
                'desc': self.technical_description or self.technical_key,
                'product': self.product_id.display_name,
            })

    def _validate_allowed_values(self):
        self.ensure_one()
        attr_lines = self.product_id.product_tmpl_id.technical_attribute_line_ids
        for tv in self.technical_value_ids:
            config = attr_lines.filtered(lambda al: al.attribute_id == tv.attribute_id)
            if not config or not config.allowed_value_ids or not tv.value_id:
                continue
            if tv.value_id not in config.allowed_value_ids:
                raise ValidationError(
                    _('El valor "%(value)s" no está permitido para %(attr)s.')
                    % {'value': tv.value_id.name, 'attr': tv.attribute_id.name}
                )

    def _get_or_create_sale_line(self):
        self.ensure_one()
        if self.sale_order_line_id:
            return self.sale_order_line_id
        return self.env['sale.order.line'].with_context(kc_from_specs_wizard=True).create({
            'order_id': self.sale_order_id.id,
            'product_id': self.product_id.id,
            'product_uom_qty': self.product_uom_qty,
        })

    def action_apply(self):
        self.ensure_one()
        if self.order_locked:
            raise UserError(_(
                'El pedido ya está confirmado. No se pueden modificar las '
                'especificaciones desde aquí.'
            ))
        self._validate_specs()
        return self._finalize_apply()

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            if not vals.get('technical_value_ids') and vals.get('product_id'):
                product = self.env['product.product'].browse(vals['product_id'])
                vals['technical_value_ids'] = self._prepare_values_from_product(product)
            prepared.append(vals)
        wizards = super().create(prepared)
        for wiz in wizards:
            if not wiz.technical_value_ids and wiz.product_id:
                wiz.write({
                    'technical_value_ids': self._prepare_values_from_product(wiz.product_id),
                })
        return wizards

    def _finalize_apply(self):
        self.ensure_one()
        sale_line = self._get_or_create_sale_line()
        self._apply_specs_to_line(sale_line)
        sale_line.with_context(kc_from_specs_wizard=True).write({
            'lot_id': False,
            'kc_lot_policy': 'production',
        })
        return {'type': 'ir.actions.act_window_close'}

    def _apply_specs_to_line(self, sale_line):
        self.ensure_one()
        commands = [(5, 0, 0)]
        for wv in self.technical_value_ids.sorted('sequence'):
            commands.append((0, 0, {
                'attribute_id': wv.attribute_id.id,
                'value_text': wv.value_text,
                'value_number': wv.value_number,
                'value_id': wv.value_id.id,
                'uom_id': wv.uom_id.id,
                'sequence': wv.sequence,
                'required': wv.required,
            }))
        sale_line.with_context(kc_from_specs_wizard=True).write({
            'product_id': self.product_id.id,
            'product_uom_qty': self.product_uom_qty,
            'technical_value_ids': commands,
        })
        sale_line._validate_allowed_technical_values()


class KcSaleLineSpecsWizardValue(models.TransientModel):
    _name = 'kc.sale.line.specs.wizard.value'
    _description = 'Valor técnico en wizard de línea'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('kc.sale.line.specs.wizard', required=True, ondelete='cascade')
    attribute_id = fields.Many2one('custom.technical.attribute', required=True)
    attribute_name = fields.Char(related='attribute_id.name', string='Característica')
    display_type = fields.Selection(related='attribute_id.display_type', readonly=True)
    allowed_value_ids = fields.Many2many(
        'custom.technical.attribute.value',
        compute='_compute_allowed_value_ids',
        string='Valores permitidos',
    )
    required = fields.Boolean(default=False)
    sequence = fields.Integer(default=10)
    value_text = fields.Char()
    value_number = fields.Float()
    value_id = fields.Many2one(
        'custom.technical.attribute.value',
        domain="[('attribute_id', '=', attribute_id)]",
    )
    uom_id = fields.Many2one('uom.uom')

    @api.depends('attribute_id', 'wizard_id.product_id')
    def _compute_allowed_value_ids(self):
        Value = self.env['custom.technical.attribute.value']
        for rec in self:
            allowed = Value
            if rec.attribute_id and rec.wizard_id.product_id:
                tmpl_lines = rec.wizard_id.product_id.product_tmpl_id.technical_attribute_line_ids
                config = tmpl_lines.filtered(
                    lambda line: line.attribute_id == rec.attribute_id
                )
                if config and config.allowed_value_ids:
                    allowed = config.allowed_value_ids
                elif rec.attribute_id:
                    allowed = Value.search([('attribute_id', '=', rec.attribute_id.id)])
            rec.allowed_value_ids = allowed

    @api.onchange('value_id')
    def _onchange_value_id(self):
        for rec in self:
            if rec.value_id and rec.display_type in ('selection', 'radio'):
                rec.value_text = False
                rec.value_number = 0.0


class KcSaleLineSpecsWizardCompatible(models.TransientModel):
    """Modelo legacy conservado por compatibilidad de datos transitorios."""
    _name = 'kc.sale.line.specs.wizard.compatible'
    _description = 'Stock compatible en wizard de specs'

    wizard_id = fields.Many2one('kc.sale.line.specs.wizard', ondelete='cascade')
    selected = fields.Boolean(string='Usar este lote')
    lot_id = fields.Many2one('stock.lot', required=True, readonly=True)
    lot_name = fields.Char(readonly=True)
    location_id = fields.Many2one('stock.location', readonly=True)
    available_qty = fields.Float(string='Disponible', readonly=True)
    technical_description = fields.Text(readonly=True)
