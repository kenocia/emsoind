# -*- coding: utf-8 -*-

import base64
import csv
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ProductTechnicalConfiguration(models.Model):
    _name = 'product.technical.configuration'
    _description = 'Configuración técnica de producto (matriz)'
    _order = 'product_tmpl_id, technical_key, id'
    _rec_name = 'configuration_key'

    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Producto',
        required=True,
        ondelete='cascade',
        index=True,
    )
    technical_value_ids = fields.One2many(
        'custom.product.technical.configuration.value',
        'configuration_id',
        string='Especificaciones',
        copy=True,
    )
    technical_key = fields.Char(
        string='Clave técnica',
        compute='_compute_technical_meta',
        store=True,
        index=True,
        readonly=True,
    )
    technical_description = fields.Text(
        string='Descripción técnica',
        compute='_compute_technical_meta',
        store=True,
        readonly=True,
    )
    configuration_key = fields.Char(
        string='Clave de configuración',
        compute='_compute_configuration_key',
        store=True,
        index=True,
    )
    legacy_sku = fields.Char(
        string='SKU legacy',
        help='Referencia histórica del catálogo (ej. BTELG24).',
        index=True,
    )
    standard_price = fields.Float(
        string='Costo estándar',
        company_dependent=True,
        digits='Product Price',
        help='Costo de catálogo para esta combinación técnica. '
             'Solo se aplica a lotes nuevos al crearse.',
    )
    weight = fields.Float(
        string='Peso (kg)',
        digits='Stock Weight',
        default=0.0,
        help='Peso unitario en kg de esta combinación técnica. '
             'Si es 0, el RP acepta 0 (sin bloquear).',
    )
    area_sqft = fields.Float(
        string='Área (FT²)',
        digits=(16, 4),
        default=0.0,
        help='Área unitaria en pies cuadrados (FT²) de esta combinación técnica. '
             'Si es 0, el RP acepta 0 (sin bloquear).',
    )
    active = fields.Boolean(default=True)
    pricelist_item_ids = fields.One2many(
        'product.pricelist.item',
        'technical_configuration_id',
        string='Reglas de precio',
    )
    has_technical_attributes = fields.Boolean(
        related='product_tmpl_id.has_technical_attributes',
    )

    _sql_constraints = [
        (
            'product_technical_key_unique',
            'unique(product_tmpl_id, technical_key)',
            'Ya existe una configuración con la misma clave técnica para este producto.',
        ),
    ]

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
        for rec in self:
            values = rec.technical_value_ids
            rec.technical_description = mixin.build_technical_description(values)
            rec.technical_key = mixin.build_technical_key(values)

    @api.depends('product_tmpl_id', 'product_tmpl_id.default_code', 'technical_key')
    def _compute_configuration_key(self):
        mixin = self.env['custom.technical.value.mixin']
        for rec in self:
            if rec.product_tmpl_id and rec.technical_key:
                prefix = rec.product_tmpl_id.default_code or str(rec.product_tmpl_id.id)
                prefix = mixin.normalize_lot_name_part(prefix, max_len=32)
                rec.configuration_key = f'{prefix}|{rec.technical_key}'
            else:
                rec.configuration_key = False

    @api.onchange('product_tmpl_id')
    def _onchange_product_tmpl_id(self):
        for rec in self:
            if rec.product_tmpl_id:
                rec.technical_value_ids = rec._prepare_value_commands_from_product(
                    rec.product_tmpl_id,
                )

    @api.model
    def _prepare_value_commands_from_product(self, product_tmpl):
        commands = [(5, 0, 0)]
        for attr_line in product_tmpl.technical_attribute_line_ids.sorted('sequence'):
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
            commands.append((0, 0, vals))
        return commands

    @api.model
    def matrix_combination_exists(self, product, technical_values):
        """Indica si la combinación de valores existe en la matriz del producto.

        Devuelve:
        - None  → el producto no tiene configuraciones técnicas (matriz vacía);
                  no hay contra qué validar, el llamador decide permitir.
        - True  → la combinación (parte de selección/radio) existe.
        - False → la combinación no existe en la matriz.
        """
        if not product:
            return None
        tmpl = product.product_tmpl_id if product._name == 'product.product' else product
        configs = self.search([
            ('product_tmpl_id', '=', tmpl.id),
            ('active', '=', True),
        ])
        if not configs:
            return None
        mixin = self.env['custom.technical.value.mixin']
        target = mixin.build_selection_key(technical_values)
        if not target:
            return None
        existing = {
            mixin.build_selection_key(config.technical_value_ids)
            for config in configs
        }
        return target in existing

    @api.model
    def find_by_product_and_key(self, product, technical_key):
        if not product or not technical_key:
            return self.browse()
        tmpl = product.product_tmpl_id if product._name == 'product.product' else product
        return self.search([
            ('product_tmpl_id', '=', tmpl.id),
            ('technical_key', '=', technical_key),
            ('active', '=', True),
        ], limit=1)

    def _kc_get_standard_price_for_lot(self, product=None):
        """Costo a sembrar en un lote nuevo según la configuración técnica."""
        self.ensure_one()
        product = product or self.product_tmpl_id.product_variant_id
        if self.standard_price:
            return self.with_company(self.env.company).standard_price
        if product:
            return product.with_company(self.env.company).standard_price
        return 0.0

    @api.model
    def _kc_resolve_weight_area(self, product, technical_key):
        """Peso (kg) y área (FT²) unitarios desde matriz; 0 si no hay config."""
        config = self.find_by_product_and_key(product, technical_key)
        if not config:
            return 0.0, 0.0
        return config.weight or 0.0, config.area_sqft or 0.0

    @api.model
    def _kc_cost_export_headers(self):
        return [
            'id',
            'product_default_code',
            'configuration_key',
            'technical_key',
            'legacy_sku',
            'standard_price',
            'weight',
            'area_sqft',
        ]

    def _kc_cost_export_row(self):
        self.ensure_one()
        return [
            self.id,
            self.product_tmpl_id.default_code or '',
            self.configuration_key or '',
            self.technical_key or '',
            self.legacy_sku or '',
            self.with_company(self.env.company).standard_price or 0.0,
            self.weight or 0.0,
            self.area_sqft or 0.0,
        ]

    def action_export_costs_csv(self):
        """Exporta la matriz técnica para cargar costos en Excel."""
        configs = self
        if not configs:
            configs = self.search([('active', '=', True)], order='product_tmpl_id, technical_key')
        else:
            configs = configs.sorted(
                key=lambda c: (c.product_tmpl_id.id, c.technical_key or '', c.id)
            )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(self._kc_cost_export_headers())
        for config in configs:
            writer.writerow(config._kc_cost_export_row())
        content = buffer.getvalue().encode('utf-8-sig')
        attachment = self.env['ir.attachment'].create({
            'name': 'configuraciones_tecnicas_costos.csv',
            'type': 'binary',
            'datas': base64.b64encode(content),
            'mimetype': 'text/csv',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    @api.model
    def _kc_parse_cost_import_value(self, raw_value):
        if raw_value is None:
            return 0.0
        text = str(raw_value).strip()
        if not text:
            return 0.0
        text = text.replace(',', '.')
        try:
            return float(text)
        except ValueError as exc:
            raise UserError(
                _('El costo "%(value)s" no es un número válido.') % {'value': raw_value}
            ) from exc

    @api.model
    def _kc_find_config_for_cost_import(self, row):
        config = self.browse()
        row_id = (row.get('id') or '').strip()
        if row_id.isdigit():
            config = self.browse(int(row_id)).exists()
            if config:
                return config

        product_code = (row.get('product_default_code') or '').strip()
        configuration_key = (row.get('configuration_key') or '').strip()
        technical_key = (row.get('technical_key') or '').strip()

        domain = []
        if product_code:
            domain.append(('product_tmpl_id.default_code', '=', product_code))
        if configuration_key:
            domain.append(('configuration_key', '=', configuration_key))
        elif technical_key:
            domain.append(('technical_key', '=', technical_key))
        else:
            return self.browse()

        return self.search(domain, limit=1)

    @api.model
    def import_costs_from_csv(self, file_content):
        """Actualiza costos de configuración desde CSV exportado por este módulo."""
        try:
            text = file_content.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = file_content.decode('latin-1')
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise UserError(_('El archivo está vacío o no tiene encabezados.'))
        missing_identity = not (
            'id' in reader.fieldnames
            or {'configuration_key', 'technical_key'} & set(reader.fieldnames)
        )
        missing_values = not (
            {'standard_price', 'weight', 'area_sqft'} & set(reader.fieldnames)
        )
        if missing_identity or missing_values:
            raise UserError(_(
                'El archivo debe incluir identificación (id o configuration_key/'
                'technical_key) y al menos una columna de valor: standard_price, '
                'weight o area_sqft.'
            ))

        updated = 0
        skipped = 0
        errors = []
        for index, row in enumerate(reader, start=2):
            config = self._kc_find_config_for_cost_import(row)
            if not config:
                skipped += 1
                errors.append(_('Fila %(row)s: configuración no encontrada.') % {'row': index})
                continue
            write_vals = {}
            if 'standard_price' in row:
                write_vals['standard_price'] = self._kc_parse_cost_import_value(
                    row.get('standard_price'))
            if 'weight' in row:
                write_vals['weight'] = self._kc_parse_cost_import_value(row.get('weight'))
            if 'area_sqft' in row:
                write_vals['area_sqft'] = self._kc_parse_cost_import_value(
                    row.get('area_sqft'))
            if not write_vals:
                skipped += 1
                errors.append(_(
                    'Fila %(row)s: sin columnas standard_price, weight o area_sqft.'
                ) % {'row': index})
                continue
            if 'standard_price' in write_vals:
                config.with_company(self.env.company).standard_price = write_vals.pop(
                    'standard_price')
            if write_vals:
                config.write(write_vals)
            updated += 1

        message = _('%s configuraciones actualizadas.') % updated
        if skipped:
            message += _(' %s filas omitidas.') % skipped
        return {
            'updated': updated,
            'skipped': skipped,
            'errors': errors[:20],
            'message': message,
        }

    @api.constrains('technical_value_ids', 'product_tmpl_id')
    def _check_allowed_technical_values(self):
        for rec in self:
            if not rec.product_tmpl_id.technical_attribute_line_ids:
                continue
            rec._validate_allowed_technical_values()

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            tmpl_id = vals.get('product_tmpl_id')
            value_commands = self._sanitize_value_commands(
                vals.get('technical_value_ids'),
            )
            if self._value_commands_need_schema(value_commands) and tmpl_id:
                value_commands = self._prepare_value_commands_from_product(
                    self.env['product.template'].browse(tmpl_id),
                )
            vals['technical_value_ids'] = value_commands
            prepared.append(vals)
        records = super().create(prepared)
        return records

    def write(self, vals):
        if 'technical_value_ids' in vals:
            vals = dict(vals)
            vals['technical_value_ids'] = self._sanitize_value_commands(
                vals['technical_value_ids'],
            )
        return super().write(vals)

    @api.model
    def _sanitize_value_commands(self, commands):
        """Normaliza líneas O2M; infiere attribute_id desde value_id si falta."""
        if not commands:
            return commands
        sanitized = []
        for command in commands:
            if command[0] != 0:
                sanitized.append(command)
                continue
            line_vals = dict(command[2])
            if not line_vals.get('attribute_id') and line_vals.get('value_id'):
                value = self.env['custom.technical.attribute.value'].browse(
                    line_vals['value_id']
                )
                line_vals['attribute_id'] = value.attribute_id.id
            if not line_vals.get('attribute_id'):
                continue
            sanitized.append((0, 0, line_vals))
        return sanitized

    @api.model
    def _value_commands_need_schema(self, commands):
        """True si no hay líneas válidas con attribute_id."""
        if not commands:
            return True
        for command in commands:
            if command[0] == 0 and command[2].get('attribute_id'):
                return False
            if command[0] == 1 and command[2].get('attribute_id'):
                return False
            if command[0] == 4:
                return False
        return True

    @api.constrains('technical_key', 'product_tmpl_id')
    def _check_technical_key_rules(self):
        for rec in self:
            if not rec.technical_key:
                raise ValidationError(
                    _('Complete las especificaciones técnicas para generar la clave de matriz.')
                )
            if not rec.product_tmpl_id:
                continue
            duplicate = self.search([
                ('product_tmpl_id', '=', rec.product_tmpl_id.id),
                ('technical_key', '=', rec.technical_key),
                ('id', '!=', rec.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    _('La clave técnica "%(key)s" ya existe para el producto "%(product)s". '
                      'Cada combinación de la matriz debe ser única dentro del mismo producto.')
                    % {
                        'key': rec.configuration_key or rec.technical_key,
                        'product': rec.product_tmpl_id.display_name,
                    }
                )

    def _validate_allowed_technical_values(self):
        self.ensure_one()
        attr_lines = self.product_tmpl_id.technical_attribute_line_ids
        for tv in self.technical_value_ids:
            config = attr_lines.filtered(lambda al: al.attribute_id == tv.attribute_id)
            if not config or not config.allowed_value_ids or not tv.value_id:
                continue
            if tv.value_id not in config.allowed_value_ids:
                raise ValidationError(
                    _('El valor "%(value)s" no está permitido para %(attr)s.')
                    % {'value': tv.value_id.name, 'attr': tv.attribute_id.name}
                )


class CustomProductTechnicalConfigurationValue(models.Model):
    _name = 'custom.product.technical.configuration.value'
    _description = 'Valor técnico en configuración de producto'
    _inherit = 'custom.technical.value.mixin'
    _order = 'sequence, id'

    configuration_id = fields.Many2one(
        'product.technical.configuration',
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

    @api.depends('attribute_id', 'configuration_id.product_tmpl_id')
    def _compute_allowed_value_ids(self):
        Value = self.env['custom.technical.attribute.value']
        for rec in self:
            allowed = Value
            if rec.attribute_id and rec.configuration_id.product_tmpl_id:
                tmpl_lines = rec.configuration_id.product_tmpl_id.technical_attribute_line_ids
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
            if rec.value_id:
                rec.attribute_id = rec.value_id.attribute_id
            if rec.value_id and rec.display_type in ('selection', 'radio'):
                rec.value_text = False
                rec.value_number = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            if not vals.get('attribute_id') and vals.get('value_id'):
                value = self.env['custom.technical.attribute.value'].browse(vals['value_id'])
                vals['attribute_id'] = value.attribute_id.id
            if not vals.get('attribute_id'):
                raise ValidationError(
                    _('Cada especificación debe tener un atributo técnico definido.')
                )
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        if vals.get('value_id') and not vals.get('attribute_id'):
            value = self.env['custom.technical.attribute.value'].browse(vals['value_id'])
            vals = dict(vals, attribute_id=value.attribute_id.id)
        return super().write(vals)
