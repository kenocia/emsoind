# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    emsoind_validated = fields.Boolean(
        string='Validado',
        copy=False,
        tracking=True,
        help='La cotización fue validada por el vendedor y espera confirmación del jefe.',
    )
    emsoind_validated_by = fields.Many2one(
        comodel_name='res.users',
        string='Validado por',
        copy=False,
        readonly=True,
    )
    emsoind_validated_date = fields.Datetime(
        string='Fecha de validación',
        copy=False,
        readonly=True,
    )
    emsoind_can_confirm = fields.Boolean(
        string='Puede confirmar',
        compute='_compute_emsoind_can_confirm',
        help='True si el usuario actual es el líder del equipo de ventas de la cotización.',
    )

    @api.depends('team_id', 'team_id.user_id', 'emsoind_validated')
    def _compute_emsoind_can_confirm(self):
        uid = self.env.user.id
        for order in self:
            leader = order.team_id.user_id
            order.emsoind_can_confirm = bool(leader and leader.id == uid)

    def _emsoind_team_leader(self):
        self.ensure_one()
        return self.team_id.user_id

    @api.model
    def _emsoind_auto_section_enabled(self):
        return self.env['res.config.settings'].emsoind_is_auto_section_by_category_enabled()

    def _emsoind_max_line_sequence(self, exclude_line=None):
        """Mayor sequence del detalle, opcionalmente excluyendo una línea."""
        self.ensure_one()
        lines = self.order_line
        if exclude_line:
            lines = lines.filtered(lambda sol: sol.id != exclude_line.id)
        return max(lines.mapped('sequence') or [0])

    def _emsoind_get_auto_section(self, category):
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: line.display_type == 'line_section'
            and line.emsoind_section_category_id == category
        )[:1]

    def _emsoind_place_line_in_category_section(self, line):
        self.ensure_one()
        category = line.product_id.categ_id
        if not category:
            return

        ctx = dict(self.env.context, emsoind_skip_auto_section=True)
        Line = self.env['sale.order.line'].with_context(**ctx)
        section = self._emsoind_get_auto_section(category)
        siblings = self.order_line.filtered(
            lambda sol: sol.id != line.id
            and sol.product_id
            and not sol.display_type
            and sol.product_id.categ_id == category
        ).sorted('sequence')

        if section:
            if siblings:
                target_seq = siblings[-1].sequence + 5
            else:
                target_seq = section.sequence + 5
            if line.sequence != target_seq:
                line.with_context(**ctx).write({'sequence': target_seq})
            if section.name != category.complete_name:
                section.write({'name': category.complete_name})
            return

        # Sección nueva: siempre al final del detalle (no arriba con sequence-5).
        max_seq = self._emsoind_max_line_sequence(exclude_line=line)
        section_seq = max_seq + 10
        section = Line.create({
            'order_id': self.id,
            'display_type': 'line_section',
            'name': category.complete_name,
            'emsoind_section_category_id': category.id,
            'sequence': section_seq,
            'price_unit': 0.0,
            'product_uom_qty': 0.0,
        })
        target_seq = section_seq + 10
        if line.sequence != target_seq:
            line.with_context(**ctx).write({'sequence': target_seq})

    def _emsoind_section_has_products(self, section):
        self.ensure_one()
        category = section.emsoind_section_category_id
        lines = self.order_line.sorted('sequence')
        after_section = False
        for order_line in lines:
            if order_line == section:
                after_section = True
                continue
            if not after_section:
                continue
            if order_line.display_type == 'line_section':
                break
            if (
                order_line.product_id
                and not order_line.display_type
                and order_line.product_id.categ_id == category
            ):
                return True
        return False

    def _emsoind_cleanup_empty_auto_sections(self):
        if not self._emsoind_auto_section_enabled():
            return
        ctx = dict(self.env.context, emsoind_skip_auto_section=True)
        for order in self:
            empty_sections = order.order_line.filtered(
                lambda line: line.display_type == 'line_section'
                and line.emsoind_section_category_id
                and not order._emsoind_section_has_products(line)
            )
            if empty_sections:
                empty_sections.with_context(**ctx).unlink()

    def _emsoind_normalize_line_sequences(self):
        ctx = dict(self.env.context, emsoind_skip_auto_section=True)
        for order in self:
            for index, line in enumerate(order.order_line.sorted('sequence'), start=1):
                sequence = index * 10
                if line.sequence != sequence:
                    line.with_context(**ctx).write({'sequence': sequence})

    def _emsoind_check_client_order_ref(self):
        if self.env.context.get('emsoind_skip_client_order_ref_check'):
            return
        for order in self:
            if order.state in ('draft', 'sent') and not (order.client_order_ref or '').strip():
                raise ValidationError(_(
                    'La referencia del cliente es obligatoria en la orden %(order)s.',
                    order=order.name,
                ))

    @api.constrains('client_order_ref', 'state')
    def _emsoind_constrain_client_order_ref(self):
        self._emsoind_check_client_order_ref()

    def copy(self, default=None):
        """Al duplicar, client_order_ref no se copia (estándar Odoo); exigir nueva referencia."""
        default = dict(default or {})
        default.setdefault('emsoind_validated', False)
        default.setdefault('emsoind_validated_by', False)
        default.setdefault('emsoind_validated_date', False)
        return super(
            SaleOrder,
            self.with_context(emsoind_skip_client_order_ref_check=True),
        ).copy(default=default)

    def _emsoind_check_validated_for_confirm(self):
        pending = self.filtered(lambda o: not o.emsoind_validated)
        if pending:
            raise UserError(_(
                'Debe validar la cotización antes de confirmarla como orden de venta.\n'
                'Pendientes: %(orders)s',
                orders=', '.join(pending.mapped('name')),
            ))

    def _emsoind_check_manager_for_confirm(self):
        """Solo el líder del equipo de la cotización puede confirmar."""
        uid = self.env.user.id
        for order in self:
            leader = order._emsoind_team_leader()
            if not leader:
                raise UserError(_(
                    'La cotización %(order)s no tiene líder de equipo de ventas. '
                    'Asigne un equipo con líder antes de confirmar.',
                    order=order.name,
                ))
            if leader.id != uid:
                raise UserError(_(
                    'Solo el líder del equipo (%(leader)s) puede confirmar '
                    'la cotización %(order)s.',
                    leader=leader.name,
                    order=order.name,
                ))

    def _emsoind_notify_managers_validated(self):
        """Avisa al líder del equipo de la cotización."""
        ActivityType = self.env.ref(
            'emsoind_sale.mail_act_emsoind_sale_validated',
            raise_if_not_found=False,
        )
        for order in self:
            leader = order._emsoind_team_leader()
            order.message_post(body=_(
                'Cotización %(order)s validada por %(user)s. '
                'Pendiente de confirmación del líder de equipo%(leader)s.',
                order=order.name,
                user=self.env.user.name,
                leader=(' (%s)' % leader.name) if leader else '',
            ))
            if not ActivityType or not leader or leader == self.env.user:
                continue
            order.activity_schedule(
                act_type_xmlid='emsoind_sale.mail_act_emsoind_sale_validated',
                user_id=leader.id,
                summary=_('Confirmar cotización validada %s') % order.name,
                note=_(
                    'La cotización %s fue validada por %s y espera su confirmación.'
                ) % (order.name, self.env.user.name),
            )

    def action_emsoind_validate(self):
        to_notify = self.browse()
        for order in self:
            if order.state not in ('draft', 'sent'):
                raise UserError(_(
                    'Solo se pueden validar cotizaciones en borrador o enviadas '
                    '(%(order)s).',
                    order=order.name,
                ))
            if order.emsoind_validated:
                continue
            if not (order.client_order_ref or '').strip():
                raise UserError(_(
                    'Indique la referencia del cliente antes de validar %(order)s.',
                    order=order.name,
                ))
            if not order.team_id or not order.team_id.user_id:
                raise UserError(_(
                    'Asigne un equipo de ventas con líder antes de validar %(order)s.',
                    order=order.name,
                ))
            order.write({
                'emsoind_validated': True,
                'emsoind_validated_by': self.env.user.id,
                'emsoind_validated_date': fields.Datetime.now(),
            })
            to_notify |= order
        to_notify._emsoind_notify_managers_validated()
        return True

    def action_emsoind_unvalidate(self):
        for order in self:
            if order.state not in ('draft', 'sent'):
                raise UserError(_(
                    'Solo se puede devolver una cotización aún no confirmada '
                    '(%(order)s).',
                    order=order.name,
                ))
            if not order.emsoind_validated:
                continue
            order.activity_unlink(['emsoind_sale.mail_act_emsoind_sale_validated'])
            order.write({
                'emsoind_validated': False,
                'emsoind_validated_by': False,
                'emsoind_validated_date': False,
            })
            order.message_post(body=_(
                'Validación revertida por %(user)s. La cotización vuelve a edición.',
                user=self.env.user.name,
            ))
        return True

    def _emsoind_check_commitment_date(self):
        missing = self.filtered(lambda o: not o.commitment_date)
        if missing:
            raise UserError(_(
                'La fecha de entrega es obligatoria para confirmar la orden.\n'
                'Pendientes: %(orders)s',
                orders=', '.join(missing.mapped('name')),
            ))

    def action_confirm(self):
        self._emsoind_check_validated_for_confirm()
        self._emsoind_check_manager_for_confirm()
        self._emsoind_check_commitment_date()
        self._emsoind_check_client_order_ref()
        partners = self.mapped('partner_id')._emsoind_sales_validation_partner()
        partners._emsoind_check_sales_required_fields()
        res = super().action_confirm()
        # Cerrar actividades de validación pendientes al confirmar.
        self.activity_unlink(['emsoind_sale.mail_act_emsoind_sale_validated'])
        return res

    # --- Orden de Producción (reporte operativo) ---

    def _emsoind_check_production_report_allowed(self):
        for order in self:
            if order.state not in ('sale', 'done'):
                raise ValidationError(_(
                    'La Orden de Producción solo puede imprimirse cuando la orden '
                    '%(order)s está confirmada.',
                    order=order.name,
                ))

    def _emsoind_get_production_shipping_partner(self):
        self.ensure_one()
        return self.partner_shipping_id or self.partner_id

    def _emsoind_get_production_report_pages(self):
        """Reutiliza paginación del reporte comercial Kenocia si está disponible."""
        self.ensure_one()
        if hasattr(self, '_get_sale_quotation_report_pages'):
            return self._get_sale_quotation_report_pages()
        lines = self._get_order_lines_to_report()
        return [lines] if lines else [lines.browse()]

    def _emsoind_get_production_report_total_qty(self):
        self.ensure_one()
        lines = self._get_order_lines_to_report().filtered(
            lambda line: not line.display_type and not line.is_downpayment,
        )
        return sum(lines.mapped('product_uom_qty'))

    def _emsoind_get_production_report_total_delivered(self):
        self.ensure_one()
        lines = self._get_order_lines_to_report().filtered(
            lambda line: not line.display_type and not line.is_downpayment,
        )
        return sum(lines.mapped('qty_delivered'))

    def _emsoind_get_production_report_total_weight(self):
        self.ensure_one()
        lines = self._get_order_lines_to_report().filtered(
            lambda line: not line.display_type and not line.is_downpayment,
        )
        return sum(line._emsoind_get_production_line_weight() for line in lines)

    def action_print_production_order(self):
        self._emsoind_check_production_report_allowed()
        return self.env.ref(
            'emsoind_sale.action_report_sale_production_order',
        ).report_action(self)
