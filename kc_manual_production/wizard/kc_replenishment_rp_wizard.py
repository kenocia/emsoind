# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class KcReplenishmentRpWizard(models.TransientModel):
    """Genera un RP de Abastecimiento desde las Reglas de Reabastecimiento.

    Carga automáticamente los productos cuyo pronóstico está por debajo del
    mínimo configurado (stock.warehouse.orderpoint.qty_to_order > 0) y permite
    al usuario ajustar la cantidad a producir antes de confirmar.
    """
    _name = 'kc.replenishment.rp.wizard'
    _description = 'Generar RP de Abastecimiento desde Reglas de Reabastecimiento'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    production_line_id = fields.Many2one(
        comodel_name='kc.production.line',
        string='Línea de Producción',
        required=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
        help="Línea responsable del abastecimiento. Se sugiere según la "
             "categoría de los productos a reponer.",
    )
    line_ids = fields.One2many(
        comodel_name='kc.replenishment.rp.wizard.line',
        inverse_name='wizard_id',
        string='Productos a Reponer',
    )

    @api.model
    def _kc_collect_replenishment_rows(self):
        """Calcula, en el servidor, las filas de reposición (productos bajo
        mínimo) en orden estable. Es la ÚNICA fuente de verdad de producto y
        especificación: tanto `default_get` (para mostrar el asistente) como
        `action_create_rp` (para crear el RP) la usan, de modo que el producto y
        la clave técnica nunca dependen de campos del formulario que el cliente
        web pudiera no persistir.

        Cada fila: dict con product (record), qty_suggested, technical_key,
        technical_description y datos de visualización.
        """
        company = self.env.company
        rows = []
        # 1) Reglas de reabastecimiento NATIVAS (productos sin especificación
        #    técnica). qty_to_order es computado: > 0 solo cuando está bajo
        #    mínimo. Los productos con atributos técnicos se excluyen aquí: se
        #    gestionan en el paso 2 (diferencian por especificación).
        orderpoints = self.env['stock.warehouse.orderpoint'].search([
            ('company_id', '=', company.id),
        ])
        for op in orderpoints:
            if op.product_id.tracking != 'lot':
                continue
            if getattr(op.product_id.product_tmpl_id, 'kc_simple_production', False):
                continue
            if self._kc_product_has_technical_attributes(op.product_id):
                continue
            qty = op.qty_to_order
            if qty > 0:
                rows.append({
                    'product': op.product_id,
                    'orderpoint_id': op.id,
                    'qty_forecast': op.qty_forecast,
                    'product_min_qty': op.product_min_qty,
                    'qty_suggested': qty,
                    'technical_key': False,
                    'technical_description': False,
                })
        # 2) Reglas de ABASTECIMIENTO TÉCNICO (kc_product_custom_specs_lot): una
        #    por configuración técnica. Lectura defensiva: si el módulo no está
        #    instalado, el modelo no existe y se omite.
        if 'kc.technical.orderpoint' in self.env:
            tech_rules = self.env['kc.technical.orderpoint'].search([
                ('company_id', '=', company.id),
                ('active', '=', True),
            ])
            for rule in tech_rules:
                if rule.product_id.tracking != 'lot':
                    continue
                qty = rule.qty_to_order_spec
                if qty > 0:
                    rows.append({
                        'product': rule.product_id,
                        'orderpoint_id': False,
                        'qty_forecast': rule.qty_on_hand_spec,
                        'product_min_qty': rule.product_min_qty,
                        'qty_suggested': qty,
                        'technical_key': rule.technical_key or False,
                        'technical_description': rule.technical_description or False,
                    })
        # Solo PT con ficha técnica: no se abastece/produce PT general desde este wizard.
        return [row for row in rows if (row.get('technical_key') or '').strip()]

    @api.model
    def _kc_default_production_line_id(self, rows=None):
        """Sugiere línea según productos del abastecimiento o fallback."""
        Entry = self.env['kc.production.entry']
        line_id = Entry._default_production_line_id()
        if line_id:
            return line_id
        rows = rows if rows is not None else self._kc_collect_replenishment_rows()
        products = self.env['product.product'].browse([
            row['product'].id for row in rows if row.get('product')
        ])
        if products:
            line = Entry._kc_resolve_production_line_for_products(
                products, company=self.env.company)
            if line:
                return line.id
        return Entry._kc_resolve_production_line_id_from_vals({
            'company_id': self.env.company.id,
        })

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        rows = self._kc_collect_replenishment_rows()
        lines = []
        for row in rows:
            lines.append((0, 0, {
                'product_id': row['product'].id,
                'orderpoint_id': row['orderpoint_id'],
                'qty_forecast': row['qty_forecast'],
                'product_min_qty': row['product_min_qty'],
                'qty_suggested': row['qty_suggested'],
                'qty_to_produce': row['qty_suggested'],
                'kc_technical_key': row['technical_key'],
                'kc_technical_description': row['technical_description'],
            }))
        res['line_ids'] = lines
        if 'production_line_id' in fields_list and not res.get('production_line_id'):
            line_id = self._kc_default_production_line_id(rows=rows)
            if line_id:
                res['production_line_id'] = line_id
        return res

    @api.model
    def _kc_product_has_technical_attributes(self, product):
        """True si el producto tiene atributos técnicos (kc_product_custom_specs_lot).
        Lectura defensiva: si el módulo no está instalado, el campo no existe.
        Control globalizado: solo se consideran técnicos los productos cuyo
        detalle es "Producto + especificaciones y lote" (kc_invoice_detail_mode)."""
        tmpl = product.product_tmpl_id
        return bool(
            getattr(tmpl, 'technical_attribute_line_ids', False)
            and getattr(tmpl, 'kc_invoice_detail_mode', False) == 'technical'
        )

    def action_create_rp(self):
        self.ensure_one()
        if not self.production_line_id:
            raise UserError(_(
                "Debe indicar la Línea de Producción antes de generar el RP."))
        # Recalculamos las filas en el servidor (fuente de verdad de producto y
        # especificación). De las líneas del asistente solo tomamos la cantidad
        # editada por el usuario (qty_to_produce, que sí se persiste),
        # emparejando por orden con las filas recalculadas. Así evitamos depender
        # de que el cliente persista product_id/technical_key en el formulario.
        rows = self._kc_collect_replenishment_rows()
        wizard_lines = self.line_ids
        entry_line_cmds = []
        for index, row in enumerate(rows):
            qty = row['qty_suggested']
            if index < len(wizard_lines):
                qty = wizard_lines[index].qty_to_produce
            if not qty or qty <= 0:
                continue
            product = row['product']
            entry_line_cmds.append((0, 0, {
                'product_id': product.id,
                'qty': qty,
                'uom_id': product.uom_id.id,
                'kc_technical_key': row['technical_key'] or False,
                'kc_technical_description': row['technical_description'] or False,
            }))
        if not entry_line_cmds:
            raise UserError(_(
                "No hay líneas con cantidad a producir mayor que cero para "
                "generar el RP de Abastecimiento."))
        rp = self.env['kc.production.entry'].create({
            'company_id': self.company_id.id,
            'production_line_id': self.production_line_id.id,
            'created_from_replenishment': True,
            'line_ids': entry_line_cmds,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Registro de Producción (Abastecimiento)'),
            'res_model': 'kc.production.entry',
            'res_id': rp.id,
            'view_mode': 'form',
            'target': 'current',
        }


class KcReplenishmentRpWizardLine(models.TransientModel):
    _name = 'kc.replenishment.rp.wizard.line'
    _description = 'Línea del Asistente de RP de Abastecimiento'

    wizard_id = fields.Many2one(
        comodel_name='kc.replenishment.rp.wizard',
        ondelete='cascade',
        required=True,
    )
    orderpoint_id = fields.Many2one(
        comodel_name='stock.warehouse.orderpoint',
        string='Regla de Reabastecimiento',
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Producto',
    )
    qty_forecast = fields.Float(
        string='Pronóstico',
        readonly=True,
        digits='Product Unit of Measure',
    )
    product_min_qty = fields.Float(
        string='Mínimo',
        readonly=True,
        digits='Product Unit of Measure',
    )
    qty_suggested = fields.Float(
        string='Cantidad Sugerida',
        readonly=True,
        digits='Product Unit of Measure',
    )
    qty_to_produce = fields.Float(
        string='Cantidad a Producir',
        digits='Product Unit of Measure',
    )
    kc_technical_key = fields.Char(
        string='Clave Técnica',
    )
    kc_technical_description = fields.Text(
        string='Especificaciones',
    )
