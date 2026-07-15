# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command


class ResPartner(models.Model):
    _inherit = 'res.partner'

    EMSOIND_SUPPLIER_DOMAIN = [
        '|', ('supplier_rank', '>', 0), ('emsoind_use_in_purchases', '=', True),
    ]
    EMSOIND_SALES_PARTNER_DOMAIN = [
        ('emsoind_use_in_sales', '=', True),
    ]

    emsoind_use_in_sales = fields.Boolean(
        string='Cliente EMSOIND',
        compute='_compute_emsoind_category_flags',
        store=True,
        index=True,
    )
    emsoind_use_in_purchases = fields.Boolean(
        string='Proveedor EMSOIND',
        compute='_compute_emsoind_category_flags',
        store=True,
        index=True,
    )
    emsoind_require_sales_fields = fields.Boolean(
        string='Requiere datos de venta',
        compute='_compute_emsoind_category_flags',
        store=True,
    )

    @api.depends(
        'category_id',
        'category_id.use_in_sales',
        'category_id.use_in_purchases',
        'category_id.require_sales_fields',
    )
    def _compute_emsoind_category_flags(self):
        for partner in self:
            tags = partner.category_id
            partner.emsoind_use_in_sales = any(tags.mapped('use_in_sales'))
            partner.emsoind_use_in_purchases = any(tags.mapped('use_in_purchases'))
            partner.emsoind_require_sales_fields = any(
                tags.mapped('require_sales_fields')
            )

    def _emsoind_is_commercial_root(self):
        """Contacto comercial raíz (contribuyente), no dirección ni contacto hijo."""
        self.ensure_one()
        return self == self.commercial_partner_id

    def _emsoind_sales_validation_partner(self):
        self.ensure_one()
        return self.commercial_partner_id or self

    def _emsoind_is_rtn_placeholder(self, vat):
        digits = ''.join(ch for ch in (vat or '') if ch.isdigit())
        return bool(digits) and set(digits) == {'0'}

    def _emsoind_check_sales_required_fields(self):
        """Valida campos obligatorios EMSOIND para clientes de ventas."""
        missing = []
        for partner in self:
            commercial = partner._emsoind_sales_validation_partner()
            if not commercial.emsoind_require_sales_fields:
                continue
            if not commercial._emsoind_is_commercial_root():
                continue

            if not commercial.name or not commercial.name.strip():
                missing.append(_('- %(partner)s: falta el nombre.', partner=commercial.display_name))
            if not commercial.country_id:
                missing.append(_('- %(partner)s: falta el país.', partner=commercial.display_name))
            if not commercial.street or not commercial.street.strip():
                missing.append(_('- %(partner)s: falta la calle/dirección.', partner=commercial.display_name))
            if not commercial.city or not commercial.city.strip():
                missing.append(_('- %(partner)s: falta la ciudad.', partner=commercial.display_name))
            if not commercial.vat or not str(commercial.vat).strip():
                missing.append(_('- %(partner)s: falta el RTN.', partner=commercial.display_name))
            elif commercial._emsoind_is_rtn_placeholder(commercial.vat):
                pass  # Consumidor Final / RTN comodín permitido
            if not commercial.phone and not commercial.mobile:
                missing.append(_(
                    '- %(partner)s: indique teléfono o celular.',
                    partner=commercial.display_name,
                ))
            if not commercial.user_id:
                missing.append(_('- %(partner)s: falta el vendedor.', partner=commercial.display_name))
            payment_term = commercial.with_company(
                commercial.company_id or self.env.company,
            ).property_payment_term_id
            if not payment_term:
                missing.append(_(
                    '- %(partner)s: falta el término de pago.',
                    partner=commercial.display_name,
                ))

        if missing:
            raise ValidationError(_(
                'Complete los datos obligatorios del cliente comercial:\n\n%s'
            ) % '\n'.join(missing))

    def _emsoind_apply_category_side_effects(self):
        """Mantiene customer_rank / supplier_rank alineados con las etiquetas."""
        for partner in self:
            vals = {}
            if partner.emsoind_use_in_sales and not partner.customer_rank:
                vals['customer_rank'] = 1
            if partner.emsoind_use_in_purchases and not partner.supplier_rank:
                vals['supplier_rank'] = 1
            if vals:
                super(ResPartner, partner).write(vals)

    @api.model
    def _emsoind_get_default_tag_for_mode(self, mode):
        xmlid_by_mode = {
            'customer': 'emsoind_sale.partner_category_cliente',
            'supplier': 'emsoind_sale.partner_category_proveedor',
        }
        xmlid = xmlid_by_mode.get(mode)
        if xmlid:
            tag = self.env.ref(xmlid, raise_if_not_found=False)
            if tag:
                return tag
        name_by_mode = {
            'customer': 'Cliente',
            'supplier': 'Proveedor',
        }
        name = name_by_mode.get(mode)
        if not name:
            return self.env['res.partner.category']
        return self.env['res.partner.category'].search([('name', '=', name)], limit=1)

    @api.model
    def _emsoind_prepare_category_commands(self, vals, mode):
        tag = self._emsoind_get_default_tag_for_mode(mode)
        if not tag:
            return vals
        commands = list(vals.get('category_id') or [])
        tag_ids = set()
        for cmd in commands:
            if not isinstance(cmd, (list, tuple)) or len(cmd) < 2:
                continue
            if cmd[0] == Command.LINK:
                tag_ids.add(cmd[1])
            elif cmd[0] == Command.SET and len(cmd) >= 3:
                tag_ids.update(cmd[2])
            elif cmd[0] == 4:
                tag_ids.add(cmd[1])
            elif cmd[0] == 6 and len(cmd) >= 3:
                tag_ids.update(cmd[2])
        if tag.id not in tag_ids:
            commands.append(Command.link(tag.id))
        vals['category_id'] = commands
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        mode = self.env.context.get('res_partner_search_mode')
        if mode in ('customer', 'supplier'):
            vals_list = [
                self._emsoind_prepare_category_commands(dict(vals), mode)
                for vals in vals_list
            ]
        partners = super().create(vals_list)
        partners._emsoind_apply_category_side_effects()
        if partners and not self.env.context.get('emsoind_skip_sales_validation'):
            partners._emsoind_check_sales_required_fields()
        return partners

    def write(self, vals):
        res = super().write(vals)
        if not self:
            return res
        if 'category_id' in vals:
            self._emsoind_apply_category_side_effects()
        if (
            not self.env.context.get('emsoind_skip_sales_validation')
            and any(key in vals for key in (
                'name', 'vat', 'country_id', 'street', 'city',
                'phone', 'mobile', 'user_id', 'property_payment_term_id',
                'category_id',
            ))
        ):
            self._emsoind_check_sales_required_fields()
        return res
