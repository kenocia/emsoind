# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'kc.pin.authorization.mixin']

    def action_confirm(self):
        for order in self:
            order._validate_technical_lines_before_confirm()
        self._kc_block_unresolved_technical_lines()
        # Flujo legacy (manual_pin): PIN y creación de lotes al confirmar.
        if self._kc_lot_creation_at_confirm_enabled():
            if not self.env.context.get('kc_pin_authorized'):
                action = self._kc_request_lot_creation_auth()
                if action:
                    return action
            emp_id = self.env.context.get('kc_pin_employee_id')
            employee = self.env['hr.employee'].browse(emp_id) if emp_id else None
            self._kc_create_pending_lots(authorized_employee=employee)
        res = super().action_confirm()
        if self._kc_lot_creation_at_confirm_enabled():
            self._kc_apply_lots_to_stock_moves()
        return res

    @api.model
    def _kc_lot_creation_at_confirm_enabled(self):
        """La creación automática de lotes al confirmar aplica solo en modo
        legacy manual_pin. Con from_rp/from_mrp los lotes los asigna producción."""
        mode = self.env['ir.config_parameter'].sudo().get_param(
            'kc_product_custom_specs_lot.lot_creation_mode', 'from_rp',
        )
        return mode == 'manual_pin'

    def _kc_pending_lot_lines(self):
        """Líneas que deben generar un lote nuevo al confirmar el pedido."""
        return self.mapped('order_line').filtered(
            lambda l: l._requires_technical_specs()
            and not l.lot_id
            and l.kc_lot_policy == 'create'
        )

    def _kc_block_unresolved_technical_lines(self):
        """Impide confirmar líneas técnicas sin especificaciones completas."""
        unresolved = self.mapped('order_line').filtered(
            lambda l: l._requires_technical_specs()
            and not l.technical_key
        )
        if not unresolved:
            return
        details = '\n'.join(
            '- %s' % line.product_id.display_name for line in unresolved
        )
        raise UserError(_(
            'Configure las especificaciones técnicas de estas líneas antes de '
            'confirmar:\n%s'
        ) % details)

    def _kc_request_lot_creation_auth(self):
        if not self._kc_lot_creation_at_confirm_enabled():
            return False
        pending = self._kc_pending_lot_lines()
        if not pending:
            return False
        require_pin = self.env['ir.config_parameter'].sudo().get_param(
            'kc_product_custom_specs_lot.require_pin_lot_creation', 'True'
        ) == 'True'
        if not require_pin:
            return False
        # Reutiliza el diálogo de PIN compartido de kc_pin_authorization
        # (teclado OWL, modo PdV, comparación segura, log y rastro en chatter).
        # Al validar, re-ejecuta action_confirm con kc_pin_authorized=True.
        return self.kc_action_require_pin(
            'action_confirm',
            reason=self._kc_build_lot_creation_message(pending),
        )

    @api.model
    def _kc_build_lot_creation_message(self, lines):
        parts = [
            _('Se crearán los siguientes lotes al confirmar el pedido:'),
        ]
        for line in lines:
            parts.append(
                '- %s: %s' % (
                    line.product_id.display_name,
                    line.technical_description or _('Sin especificación'),
                )
            )
        return '\n'.join(parts)

    def _kc_create_pending_lots(self, authorized_employee=None):
        if not self._kc_lot_creation_at_confirm_enabled():
            return
        Lot = self.env['stock.lot']
        for order in self:
            for line in order._kc_pending_lot_lines():
                lot = Lot._get_or_create_for_sale_line(
                    line, authorized_employee=authorized_employee,
                )
                line.with_context(kc_from_specs_wizard=True).write({'lot_id': lot.id})

    def _kc_apply_lots_to_stock_moves(self):
        for order in self:
            for line in order.order_line:
                if line.lot_id:
                    line._kc_propagate_lot_to_stock_moves()

    def _validate_technical_lines_before_confirm(self):
        for order in self:
            for line in order.order_line:
                if line._requires_technical_specs():
                    line._validate_required_technical_values()
                    line._validate_combination_in_matrix()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    technical_value_ids = fields.One2many(
        'custom.sale.order.line.technical.value',
        'sale_order_line_id',
        string='Especificaciones técnicas',
        copy=True,
    )
    technical_description = fields.Text(
        string='Descripción técnica',
        compute='_compute_technical_meta',
        store=True,
        readonly=True,
    )
    technical_key = fields.Char(
        string='Clave técnica',
        compute='_compute_technical_meta',
        store=True,
        index=True,
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lote seleccionado',
        domain="[('product_id', '=', product_id)]",
        copy=False,
    )
    kc_lot_policy = fields.Selection(
        selection=[
            ('existing', 'Lote existente'),
            ('create', 'Crear lote al confirmar'),
            ('production', 'Se define en producción'),
        ],
        string='Política de lote',
        copy=False,
    )
    compatible_lot_qty = fields.Float(
        string='Stock compatible',
        compute='_compute_compatible_stock',
    )
    has_compatible_stock = fields.Boolean(
        string='Tiene stock compatible',
        compute='_compute_compatible_stock',
    )
    technical_specs_filled = fields.Boolean(
        compute='_compute_technical_specs_filled',
    )
    show_technical_section = fields.Boolean(
        compute='_compute_show_technical_section',
    )

    @api.depends('product_id', 'product_id.product_tmpl_id.technical_attribute_line_ids',
                 'product_id.product_tmpl_id.kc_invoice_detail_mode')
    def _compute_show_technical_section(self):
        for line in self:
            line.show_technical_section = line._has_technical_attributes_template()

    @api.depends('technical_value_ids', 'technical_value_ids.value_id',
                 'technical_value_ids.value_text', 'technical_value_ids.value_number')
    def _compute_technical_specs_filled(self):
        for line in self:
            line.technical_specs_filled = any(
                line._technical_value_is_set(tv) for tv in line.technical_value_ids
            )

    @api.depends(
        'technical_value_ids',
        'technical_value_ids.value_id',
        'technical_value_ids.value_text',
        'technical_value_ids.value_number',
        'technical_value_ids.attribute_id',
        'technical_value_ids.uom_id',
    )
    def _compute_technical_meta(self):
        mixin = self.env['custom.technical.value.mixin']
        for line in self:
            values = line.technical_value_ids
            line.technical_description = mixin.build_technical_description(values)
            line.technical_key = mixin.build_technical_key(values)

    @api.depends('product_id', 'technical_key')
    def _compute_compatible_stock(self):
        for line in self:
            qty = 0.0
            if line.product_id and line.technical_key:
                lots = line._search_compatible_lots(require_qty=False)
                qty = sum(lots.mapped('product_qty'))
            line.compatible_lot_qty = qty
            line.has_compatible_stock = qty > 0

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if self.env.context.get('kc_from_specs_wizard'):
            return lines
        for line, vals in zip(lines, vals_list):
            if (
                vals.get('product_id')
                and not vals.get('technical_value_ids')
                and line._has_technical_attributes_template()
                and not self._kc_auto_open_specs_wizard()
            ):
                line._load_technical_attributes_from_product()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if 'lot_id' in vals:
            self.filtered('lot_id')._kc_propagate_lot_to_stock_moves()
        if self.env.context.get('kc_from_specs_wizard'):
            return res
        if 'product_id' in vals:
            for line in self:
                if line._has_technical_attributes_template() and not self._kc_auto_open_specs_wizard():
                    line._load_technical_attributes_from_product()
        return res

    def _kc_propagate_lot_to_stock_moves(self):
        """Propaga el lote de la OV a entregas (solo líneas legacy con lote fijo)."""
        for line in self:
            if not line.lot_id:
                continue
            if line.kc_lot_policy == 'production':
                continue
            moves = line.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
                and m.picking_type_id.code == 'outgoing'
            )
            if not moves:
                continue
            moves.write({'kc_lot_id': line.lot_id.id})
            moves._kc_reassign_restricted_lot()

    @api.model
    def _kc_auto_open_specs_wizard(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'kc_product_custom_specs_lot.auto_open_specs_wizard', 'True'
        ) == 'True'

    @api.onchange('product_id')
    def _onchange_product_id_technical(self):
        if not self.product_id:
            self.technical_value_ids = [(5, 0, 0)]
            self.lot_id = False
            self.kc_lot_policy = False
            return
        if not self._has_technical_attributes_template():
            return
        self.technical_value_ids = [(5, 0, 0)]
        self.lot_id = False
        self.kc_lot_policy = False

    def _has_technical_attributes_template(self):
        self.ensure_one()
        if not self.product_id:
            return False
        tmpl = self.product_id.product_tmpl_id
        return bool(
            tmpl.technical_attribute_line_ids
            and tmpl.kc_invoice_detail_mode == 'technical'
        )

    def _load_technical_attributes_from_product(self):
        self.ensure_one()
        if not self.product_id:
            return
        self.write({
            'technical_value_ids': self._prepare_technical_value_commands_from_product(),
            'lot_id': False,
            'kc_lot_policy': False,
        })

    def _prepare_technical_value_commands_from_product(self):
        self.ensure_one()
        tmpl = self.product_id.product_tmpl_id
        commands = [(5, 0, 0)]
        for attr_line in tmpl.technical_attribute_line_ids.sorted('sequence'):
            attr = attr_line.attribute_id
            vals = {
                'attribute_id': attr.id,
                'sequence': attr_line.sequence,
                'required': attr_line.required,
                'uom_id': attr.uom_id.id,
            }
            default = attr_line.default_value_id
            if default:
                if attr.display_type in ('selection', 'radio'):
                    if not attr_line.allowed_value_ids or default in attr_line.allowed_value_ids:
                        vals['value_id'] = default.id
                elif attr.display_type == 'text':
                    vals['value_text'] = default.name
            commands.append((0, 0, vals))
        return commands

    def _requires_technical_specs(self):
        self.ensure_one()
        if not self.product_id:
            return False
        product = self.product_id
        tmpl = product.product_tmpl_id
        if not tmpl.technical_attribute_line_ids:
            return False
        if tmpl.kc_invoice_detail_mode != 'technical':
            return False
        return product.is_storable and product.tracking == 'lot'

    def _technical_value_is_set(self, tech_value):
        attr = tech_value.attribute_id
        if attr.display_type == 'numeric':
            return bool(tech_value.value_number)
        if attr.display_type in ('selection', 'radio'):
            return bool(tech_value.value_id)
        return bool(tech_value.value_text and tech_value.value_text.strip())

    def _validate_required_technical_values(self):
        self.ensure_one()
        missing = []
        for tv in self.technical_value_ids.filtered('required'):
            if not self._technical_value_is_set(tv):
                missing.append(tv.attribute_id.name)
        if missing:
            raise ValidationError(
                _('Complete las especificaciones obligatorias en la línea de %(product)s: %(attrs)s')
                % {'product': self.product_id.display_name, 'attrs': ', '.join(missing)}
            )
        if not self.technical_key:
            raise ValidationError(
                _('La línea de %(product)s no tiene clave técnica válida.')
                % {'product': self.product_id.display_name}
            )

    def _validate_allowed_technical_values(self):
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

    def _validate_combination_in_matrix(self):
        """Bloquea líneas cuya combinación no exista en la matriz técnica.

        Solo las combinaciones dadas de alta como configuración técnica son
        producibles. Si el producto no tiene matriz definida, no se bloquea."""
        self.ensure_one()
        exists = self.env['product.technical.configuration'].matrix_combination_exists(
            self.product_id, self.technical_value_ids,
        )
        if exists is False:
            raise ValidationError(_(
                'La línea de "%(product)s" tiene una combinación "%(desc)s" que '
                'no está dada de alta como configuración técnica y no puede '
                'producirse. Configure una combinación válida antes de confirmar.'
            ) % {
                'product': self.product_id.display_name,
                'desc': self.technical_description or self.technical_key,
            })

    def _search_compatible_lots(self, require_qty=True):
        self.ensure_one()
        domain = [
            ('product_id', '=', self.product_id.id),
            ('technical_key', '=', self.technical_key),
        ]
        lots = self.env['stock.lot'].search(domain)
        if require_qty:
            lots = lots.filtered(lambda lot: lot.product_qty > 0)
        return lots

    def _prepare_compatible_stock_lines(self):
        self.ensure_one()
        lines = []
        Quant = self.env['stock.quant']
        lots = self._search_compatible_lots(require_qty=True)
        for lot in lots:
            quants = Quant.search([
                ('lot_id', '=', lot.id),
                ('product_id', '=', self.product_id.id),
                ('quantity', '>', 0),
                ('location_id.usage', '=', 'internal'),
            ])
            for quant in quants:
                lines.append({
                    'lot_id': lot.id,
                    'location_id': quant.location_id.id,
                    'available_qty': quant.available_quantity,
                    'technical_description': lot.technical_description,
                })
        if not lines:
            for lot in lots:
                lines.append({
                    'lot_id': lot.id,
                    'available_qty': lot.product_qty,
                    'technical_description': lot.technical_description,
                })
        return lines

    def action_kc_auto_open_specs_wizard(self):
        """Devuelve la acción del wizard de especificaciones solo si el producto
        tiene atributos técnicos y la apertura automática está habilitada.
        Pensado para ser invocado desde el widget de producto (JS), replicando
        el comportamiento del configurador de variantes de Odoo."""
        self.ensure_one()
        if not self._has_technical_attributes_template():
            return False
        if not self._kc_auto_open_specs_wizard():
            return False
        return self.action_open_specs_wizard()

    def action_open_specs_wizard(self):
        self.ensure_one()
        if not self.product_id and not self.env.context.get('default_product_id'):
            raise UserError(_('Seleccione un producto primero.'))
        return {
            'name': _('Configurar producto'),
            'type': 'ir.actions.act_window',
            'res_model': 'kc.sale.line.specs.wizard',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_sale_order_id': self.order_id.id,
                'default_sale_order_line_id': self.id if self.id else False,
                'default_product_id': self.product_id.id,
                'default_product_uom_qty': self.product_uom_qty or 1.0,
            },
        }

    def action_copy_technical_specs(self):
        self.ensure_one()
        if not self.order_id:
            raise UserError(_('La línea debe pertenecer a un pedido de venta.'))
        return {
            'name': _('Copiar especificaciones'),
            'type': 'ir.actions.act_window',
            'res_model': 'kc.copy.technical.specs.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_target_line_id': self.id,
                'default_sale_order_id': self.order_id.id,
            },
        }

    def _prepare_procurement_values(self, group_id=False):
        values = super()._prepare_procurement_values(group_id=group_id)
        if self.lot_id:
            values['kc_lot_id'] = self.lot_id.id
        return values

    def _copy_technical_values_from_line(self, source_line):
        self.ensure_one()
        commands = [(5, 0, 0)]
        for tv in source_line.technical_value_ids.sorted('sequence'):
            commands.append((0, 0, {
                'attribute_id': tv.attribute_id.id,
                'value_text': tv.value_text,
                'value_number': tv.value_number,
                'value_id': tv.value_id.id,
                'uom_id': tv.uom_id.id,
                'sequence': tv.sequence,
                'required': tv.required,
            }))
        self.with_context(kc_from_specs_wizard=True).write({
            'technical_value_ids': commands,
            'lot_id': source_line.lot_id.id if source_line.lot_id else False,
            'kc_lot_policy': source_line.kc_lot_policy,
        })

    def _kc_get_delivered_lot_names(self):
        """Nombres de lotes despachados (multi-lote) o vacío si aún no hay entrega."""
        self.ensure_one()
        lots = self.env['stock.lot']
        moves = self.move_ids.filtered(
            lambda m: m.state == 'done' and m.picking_type_id.code == 'outgoing'
        )
        for move in moves:
            lots |= move.move_line_ids.filtered(
                lambda ml: ml.lot_id and ml.quantity > 0
            ).mapped('lot_id')
        return lots.mapped('name')

    def _kc_get_compatible_reserved_qty_for_line(self, warehouse=None):
        """Cantidad ya reservada para entregas de esta línea con lotes compatibles."""
        self.ensure_one()
        if not self.product_id or not self.technical_key:
            return 0.0
        moves = self.env['stock.move'].search([
            ('sale_line_id', '=', self.id),
            ('state', 'not in', ('done', 'cancel')),
            ('product_id', '=', self.product_id.id),
        ])
        stock_locations = self.env['stock.location']
        if warehouse:
            stock_locations = self.env['stock.location'].search([
                ('id', 'child_of', warehouse.lot_stock_id.id),
            ])
        total = 0.0
        for move in moves:
            for ml in move.move_line_ids:
                if not ml.lot_id or ml.lot_id.technical_key != self.technical_key:
                    continue
                if stock_locations and ml.location_id not in stock_locations:
                    continue
                total += ml.quantity
        return total

    def _kc_get_compatible_available_qty(self, warehouse=None):
        """Stock libre + reservado para esta línea, con la misma clave técnica."""
        self.ensure_one()
        if not self.product_id or not self.technical_key:
            return 0.0
        domain = [
            ('product_id', '=', self.product_id.id),
            ('lot_id', '!=', False),
            ('lot_id.technical_key', '=', self.technical_key),
            ('quantity', '>', 0),
            ('location_id.usage', '=', 'internal'),
        ]
        if warehouse:
            domain.append(('location_id', 'child_of', warehouse.lot_stock_id.id))
        quants = self.env['stock.quant'].search(domain)
        available = sum(quants.mapped('available_quantity'))
        reserved_own = self._kc_get_compatible_reserved_qty_for_line(warehouse)
        return available + reserved_own

    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        if not self.product_id:
            return vals
        tmpl = self.product_id.product_tmpl_id
        if tmpl.kc_invoice_detail_mode == 'technical':
            parts = [self.product_id.display_name]
            if self.technical_description:
                parts.append(self.technical_description)
            lot_names = self._kc_get_delivered_lot_names()
            if lot_names:
                parts.append(_('Lote: %s') % ', '.join(lot_names))
            elif self.lot_id:
                parts.append(_('Lote: %s') % self.lot_id.name)
            vals['name'] = '\n'.join(parts)
        else:
            # Conservar descripción comercial de la OV (name multilínea);
            # no truncar al solo display_name del producto.
            line_name = (self.name or '').strip()
            vals['name'] = line_name or self.product_id.display_name
        return vals

    @api.constrains('technical_value_ids', 'product_id')
    def _check_allowed_technical_values(self):
        for line in self:
            if line.env.context.get('kc_from_specs_wizard'):
                continue
            line._validate_allowed_technical_values()

    def _kc_get_technical_configuration(self):
        self.ensure_one()
        if not self.product_id or not self.technical_key:
            return self.env['product.technical.configuration']
        return self.env['product.technical.configuration'].find_by_product_and_key(
            self.product_id,
            self.technical_key,
        )

    def _kc_resolve_unit_cost(self):
        """Costo unitario según lote, matriz técnica o producto genérico."""
        self.ensure_one()
        if not self.product_id:
            return 0.0
        cost = self.env['stock.lot']._kc_resolve_unit_cost(
            self.product_id,
            technical_key=self.technical_key,
            lot=self.lot_id,
            company=self.company_id,
        )
        return self.product_id.uom_id._compute_price(cost, self.product_uom)

    @api.depends(
        'product_id',
        'product_uom',
        'product_uom_qty',
        'price_subtotal',
        'technical_key',
        'lot_id',
        'lot_id.standard_price',
    )
    def _compute_kc_cost_margin(self):
        for line in self:
            if not line.product_id or line.display_type:
                line.kc_unit_cost = 0.0
                line.kc_margin = 0.0
                line.kc_margin_percent = 0.0
                continue
            unit_cost = line._kc_resolve_unit_cost()
            qty = line.product_uom_qty or 0.0
            line.kc_unit_cost = unit_cost
            line.kc_margin = line.price_subtotal - (unit_cost * qty)
            line.kc_margin_percent = (
                line.price_subtotal and line.kc_margin / line.price_subtotal
            )

    kc_unit_cost = fields.Float(
        string='Costo unitario',
        compute='_compute_kc_cost_margin',
        digits='Product Price',
        groups='base.group_user',
    )
    kc_margin = fields.Monetary(
        string='Margen',
        compute='_compute_kc_cost_margin',
        currency_field='currency_id',
        groups='base.group_user',
    )
    kc_margin_percent = fields.Float(
        string='Margen (%)',
        compute='_compute_kc_cost_margin',
        groups='base.group_user',
    )

    def _get_display_price(self):
        """Inyecta la clave técnica en el contexto para que todo el cálculo de
        precio (incluida la resolución de reglas de listas de precios derivadas
        de otra lista) pueda emparejar la matriz por technical_key."""
        if self.technical_key:
            self = self.with_context(kc_technical_key=self.technical_key)
        return super()._get_display_price()

    @api.depends(
        'product_id',
        'product_uom',
        'product_uom_qty',
        'technical_key',
    )
    def _compute_pricelist_item_id(self):
        for line in self:
            if not line.product_id or line.display_type or not line.order_id.pricelist_id:
                line.pricelist_item_id = False
            else:
                line.pricelist_item_id = line.order_id.pricelist_id._get_product_rule(
                    line.product_id,
                    quantity=line.product_uom_qty or 1.0,
                    uom=line.product_uom,
                    date=line._get_order_date(),
                    technical_key=line.technical_key or False,
                )

    @api.depends(
        'product_id',
        'product_uom',
        'product_uom_qty',
        'technical_key',
        'technical_value_ids',
        'technical_value_ids.value_id',
        'technical_value_ids.attribute_id',
    )
    def _compute_price_unit(self):
        return super()._compute_price_unit()
