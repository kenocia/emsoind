# -*- coding: utf-8 -*-

import itertools

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Tope de seguridad para evitar una explosión combinatoria al generar la matriz.
MAX_MATRIX_COMBINATIONS = 2000


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    technical_attribute_line_ids = fields.One2many(
        'custom.product.technical.attribute.line',
        'product_tmpl_id',
        string='Atributos técnicos',
        copy=True,
    )
    has_technical_attributes = fields.Boolean(
        compute='_compute_has_technical_attributes',
    )
    kc_invoice_detail_mode = fields.Selection(
        selection=[
            ('product_only', 'Solo producto (sin medidas ni lote)'),
            ('technical', 'Producto + especificaciones y lote'),
        ],
        string='Detalle en factura',
        default='product_only',
        help='Define qué información se muestra en factura, cotización y pedido impresos.',
    )
    technical_configuration_ids = fields.One2many(
        'product.technical.configuration',
        'product_tmpl_id',
        string='Configuraciones técnicas (matriz)',
    )

    def _compute_has_technical_attributes(self):
        for tmpl in self:
            tmpl.has_technical_attributes = bool(tmpl.technical_attribute_line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._kc_apply_technical_product_defaults()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(field in vals for field in ('technical_attribute_line_ids', 'kc_invoice_detail_mode')):
            self._kc_apply_technical_product_defaults()
        return res

    def _kc_requires_technical_lot_setup(self):
        self.ensure_one()
        return bool(self.technical_attribute_line_ids) or self.kc_invoice_detail_mode == 'technical'

    def _kc_apply_technical_product_defaults(self):
        """Productos técnicos deben rastrearse y valorarse por lote."""
        for tmpl in self.filtered(lambda t: t._kc_requires_technical_lot_setup()):
            updates = {}
            if tmpl.tracking != 'lot':
                updates['tracking'] = 'lot'
            if not tmpl.lot_valuated:
                updates['lot_valuated'] = True
            if updates:
                super(ProductTemplate, tmpl).write(updates)

    def action_add_technical_configuration(self):
        self.ensure_one()
        return {
            'name': _('Nueva configuración técnica'),
            'type': 'ir.actions.act_window',
            'res_model': 'product.technical.configuration',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_tmpl_id': self.id,
            },
        }

    def action_generate_technical_matrix(self):
        """Genera todas las configuraciones técnicas (producto cartesiano) a
        partir de la tabla de atributos del producto.

        Reglas (acordadas con el usuario):
        - Solo combina atributos de selección/radio que tengan "valores
          permitidos" definidos en la línea. Si alguno carece de ellos, se
          bloquea para que el usuario los defina primero.
        - Los atributos numéricos/texto se omiten (las configuraciones se
          generan sin ese valor).
        - Las combinaciones que ya existen para el producto se saltan.
        - El SKU (legacy_sku) se deja vacío.
        """
        self.ensure_one()
        attr_lines = self.technical_attribute_line_ids.sorted('sequence')
        if not attr_lines:
            raise UserError(_('El producto no tiene atributos técnicos definidos.'))

        axes = []
        missing_allowed = []
        skipped_attrs = []
        for line in attr_lines:
            attr = line.attribute_id
            if attr.display_type in ('selection', 'radio'):
                if not line.allowed_value_ids:
                    missing_allowed.append(attr.display_name)
                    continue
                values = line.allowed_value_ids.sorted(lambda v: (v.sequence, v.id))
                axes.append((line, values))
            else:
                skipped_attrs.append(attr.display_name)

        if missing_allowed:
            raise UserError(_(
                'Defina los "valores permitidos" de los siguientes atributos de '
                'selección antes de generar la matriz:\n- %s'
            ) % '\n- '.join(missing_allowed))

        if not axes:
            raise UserError(_(
                'No hay atributos de selección con valores permitidos para '
                'generar la matriz.'
            ))

        total_combos = 1
        for _line, values in axes:
            total_combos *= len(values)
        if total_combos > MAX_MATRIX_COMBINATIONS:
            raise UserError(_(
                'La generación produciría %(total)s combinaciones, lo que supera '
                'el límite de %(limit)s. Reduzca los valores permitidos o cree las '
                'configuraciones manualmente.'
            ) % {'total': total_combos, 'limit': MAX_MATRIX_COMBINATIONS})

        Config = self.env['product.technical.configuration']
        mixin = self.env['custom.technical.value.mixin']
        existing_keys = set(Config.with_context(active_test=False).search([
            ('product_tmpl_id', '=', self.id),
        ]).mapped('technical_key'))

        to_create = []
        skipped_existing = 0
        for combo in itertools.product(*[values for _line, values in axes]):
            value_commands = []
            key_parts = []
            for (line, _values), value in zip(axes, combo):
                attr = line.attribute_id
                value_commands.append((0, 0, {
                    'attribute_id': attr.id,
                    'sequence': line.sequence,
                    'required': line.required,
                    'uom_id': attr.uom_id.id,
                    'value_id': value.id,
                }))
                code = (attr.code or attr.name or '').strip().upper()
                val = mixin._normalize_token(value.code or value.name)
                if code and val:
                    key_parts.append(f'{code}={val}')
            key = '|'.join(key_parts)
            if key in existing_keys:
                skipped_existing += 1
                continue
            existing_keys.add(key)
            to_create.append({
                'product_tmpl_id': self.id,
                'technical_value_ids': value_commands,
            })

        if to_create:
            Config.create(to_create)

        message = _('%(created)s configuraciones creadas.') % {'created': len(to_create)}
        if skipped_existing:
            message += _(' %(skipped)s ya existían (omitidas).') % {'skipped': skipped_existing}
        if skipped_attrs:
            message += _(
                '\nAtributos numéricos/texto omitidos: %s.'
            ) % ', '.join(skipped_attrs)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Matriz técnica'),
                'message': message,
                'type': 'success' if to_create else 'warning',
                'sticky': bool(skipped_attrs),
            },
        }

    @api.constrains('technical_attribute_line_ids', 'tracking', 'lot_valuated', 'kc_invoice_detail_mode')
    def _check_technical_requires_lot_tracking(self):
        for tmpl in self:
            if not tmpl._kc_requires_technical_lot_setup():
                continue
            if tmpl.tracking != 'lot':
                raise ValidationError(
                    _('El producto "%(name)s" tiene configuración técnica: '
                      'debe configurarse con rastreo por lote.')
                    % {'name': tmpl.display_name}
                )
            if not tmpl.lot_valuated:
                raise ValidationError(
                    _('El producto "%(name)s" tiene configuración técnica: '
                      'debe activarse la valoración por lote/serie.')
                    % {'name': tmpl.display_name}
                )
