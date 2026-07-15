# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


class AccountTax(models.Model):
    _inherit = 'account.tax'

    codigo_sar_id = fields.Many2one(
        'kc_fiscal_hn.codigo.sar',
        string='Código SAR Honduras',
        domain="[('tipo_uso', 'in', ['all', type_tax_use]), ('activo', '=', True)]",
        help='Código oficial SAR Honduras. '
             'Se filtra según el tipo de impuesto '
             '(ventas o compras).',
    )
    codigo_sar = fields.Char(
        string='Código SAR',
        related='codigo_sar_id.codigo',
        store=True,
        readonly=True,
        help='Código numérico SAR (calculado '
             'desde la tabla de códigos).',
    )
    tipo_impuesto = fields.Selection([
        ('isv', 'ISV'),
        ('retencion', 'Retención'),
        ('exento', 'Exento'),
        ('exonerado', 'Exonerado'),
        ('otros', 'Otros'),
    ], string='Tipo de Impuesto SAR', default='isv')

    es_deducible = fields.Boolean(
        string='Es Deducible',
        default=True,
        help='Indica si el impuesto es deducible para efectos fiscales',
    )
    aplica_retencion = fields.Boolean(
        string='Aplica Retención',
        default=False,
        help='Indica si este impuesto aplica retención',
    )
    is_retention = fields.Boolean(
        string='Es Retención',
        default=False,
        help='Indica si este impuesto es de retención',
    )

    def _register_hook(self):
        super()._register_hook()
        self._migrate_codigo_sar_links()
        self._cleanup_generic_tax_sar_links()
        self._sync_fiscal_hn_invoice_labels()

    @api.model
    def _fiscal_hn_invoice_label(self, nombre):
        """Etiqueta en facturas: el nombre del impuesto sin el sufijo ' HN'."""
        if not nombre:
            return nombre
        return nombre.removesuffix(' HN').strip()

    @api.model
    def _sync_fiscal_hn_invoice_labels(self):
        """Actualiza 'Etiqueta en facturas' de los impuestos HN existentes.

        Deja la etiqueta igual al nombre pero sin el sufijo ' HN'
        (p. ej. 'ISV 15% HN' -> 'ISV 15%'). Idempotente: se ejecuta en cada
        actualización del módulo.
        """
        if 'invoice_label' not in self._fields:
            return
        taxes = self.with_context(active_test=False).search([
            ('name', '=like', '% HN'),
        ])
        actualizados = 0
        for tax in taxes:
            label = self._fiscal_hn_invoice_label(tax.name)
            if tax.invoice_label != label:
                tax.invoice_label = label
                actualizados += 1
        if actualizados:
            _logger.info(
                "Etiqueta en facturas actualizada en %d impuesto(s) HN.",
                actualizados,
            )

    @api.model
    def _cleanup_generic_tax_sar_links(self):
        """Quita código SAR de impuestos genéricos Odoo (15%, 18%)."""
        generic = self.search([
            ('codigo_sar_id', '!=', False),
            '|',
            ('name', '=ilike', '15%'),
            ('name', '=ilike', '18%'),
        ]).filtered(
            lambda t: t.name in ('15%', '18%'),
        )
        if generic:
            generic.write({'codigo_sar_id': False})
            _logger.info(
                'Limpieza SAR: %d impuesto(s) genéricos Odoo '
                'desvinculados de códigos SAR.',
                len(generic),
            )

    @api.model
    def _migrate_codigo_sar_links(self):
        """Vincula impuestos existentes a códigos SAR por código alfanumérico."""
        cr = self.env.cr
        cr.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'account_tax'
              AND column_name = 'codigo_sar_id'
        """)
        if not cr.fetchone():
            return

        cr.execute("""
            SELECT t.id, t.codigo_sar
            FROM account_tax t
            WHERE t.codigo_sar IS NOT NULL
              AND t.codigo_sar != ''
              AND t.codigo_sar_id IS NULL
        """)
        rows = cr.fetchall()
        if not rows:
            return

        CodigoSAR = self.env['kc_fiscal_hn.codigo.sar']
        linked = 0
        for tax_id, codigo in rows:
            tax = self.browse(tax_id)
            if tax.name in ('15%', '18%'):
                continue
            codigo_rec = CodigoSAR.search([('codigo', '=', codigo)], limit=1)
            if codigo_rec:
                cr.execute(
                    'UPDATE account_tax SET codigo_sar_id = %s WHERE id = %s',
                    (codigo_rec.id, tax_id),
                )
                linked += 1

        if linked:
            _logger.info(
                'Migración SAR: %d impuesto(s) vinculados a códigos SAR.',
                linked,
            )

    @api.onchange('codigo_sar_id')
    def _onchange_codigo_sar_id(self):
        if not self.codigo_sar_id:
            return
        codigo = self.codigo_sar_id
        self.tipo_impuesto = codigo.tipo_impuesto
        if codigo.porcentaje is not False:
            self.amount = codigo.porcentaje
        self.is_retention = codigo.tipo_impuesto == 'retencion'
        self.aplica_retencion = codigo.tipo_impuesto == 'retencion'
        self.es_deducible = codigo.tipo_impuesto in ('isv', 'retencion')

    @api.model
    def _fiscal_hn_tax_group_name(self, tipo, amount):
        """Nombre del grupo de impuestos usado en reportes y productos HN."""
        if tipo == 'exento':
            return 'Exento'
        if tipo == 'exonerado':
            return 'Exonerado'
        if tipo == 'isv' and float_compare(amount, 18.0, precision_digits=2) == 0:
            return '18%'
        if tipo == 'isv':
            return '15%'
        return 'Otros'

    @api.model
    def _get_fiscal_hn_tax_group(self, company, tipo, amount):
        """Obtiene o crea el grupo de impuestos requerido por Odoo 18."""
        TaxGroup = self.env['account.tax.group'].with_company(company)
        target_name = self._fiscal_hn_tax_group_name(tipo, amount)
        group = TaxGroup.search([
            ('name', '=', target_name),
            ('company_id', '=', company.id),
        ], limit=1)
        if group:
            return group
        return TaxGroup.create({
            'name': target_name,
            'company_id': company.id,
        })

    @api.model
    def _init_fiscal_hn_taxes(self):
        """Crea el catálogo de impuestos fiscales de Honduras.

        Los impuestos llevan el sufijo ``HN`` para no chocar con los impuestos
        genéricos de Odoo (``15%``, ``18%``) y cumplen con las reglas del módulo
        fiscal: ``tipo_impuesto`` y ``codigo_sar_id`` correctos.

        Es idempotente: omite los que ya existen (por nombre + compañía + tipo
        de uso), por lo que puede ejecutarse en cada actualización del módulo.
        """
        ref = self.env.ref

        def cod(xmlid):
            rec = ref('kc_fiscal_hn_v18.%s' % xmlid, raise_if_not_found=False)
            return rec.id if rec else False

        # (nombre, amount, type_tax_use, tipo_impuesto, codigo_sar, es_deducible)
        plantillas = [
            ('ISV 15% HN', 15.0, 'sale', 'isv', cod('codigo_sar_01'), True),
            ('ISV 18% HN', 18.0, 'sale', 'isv', cod('codigo_sar_02'), True),
            ('Exento HN', 0.0, 'sale', 'exento', cod('codigo_sar_03'), False),
            ('Exonerado HN', 0.0, 'sale', 'exonerado', cod('codigo_sar_04'), False),
            ('ISV 15% Compra HN', 15.0, 'purchase', 'isv', cod('codigo_sar_06'), True),
            ('ISV 18% Compra HN', 18.0, 'purchase', 'isv', cod('codigo_sar_07'), True),
            ('Exento Compra HN', 0.0, 'purchase', 'exento', cod('codigo_sar_03'), False),
        ]

        companias = self.env['res.company'].search([])
        creados = 0
        for company in companias:
            Tax = self.with_company(company)
            for nombre, amount, uso, tipo, codigo_id, deducible in plantillas:
                existe = Tax.with_context(active_test=False).search([
                    ('name', '=', nombre),
                    ('company_id', '=', company.id),
                    ('type_tax_use', '=', uso),
                ], limit=1)
                if existe:
                    continue
                tax_group = self._get_fiscal_hn_tax_group(company, tipo, amount)
                vals = {
                    'name': nombre,
                    'amount': amount,
                    'amount_type': 'percent',
                    'type_tax_use': uso,
                    'company_id': company.id,
                    'tax_group_id': tax_group.id,
                    'tipo_impuesto': tipo,
                    'codigo_sar_id': codigo_id,
                    'es_deducible': deducible,
                }
                if 'invoice_label' in self._fields:
                    vals['invoice_label'] = self._fiscal_hn_invoice_label(nombre)
                Tax.create(vals)
                creados += 1

        if creados:
            _logger.info('Impuestos fiscales HN creados: %d.', creados)

    @api.model
    def _get_fiscal_taxes(self, tax_type=None):
        """Obtiene impuestos fiscales según el tipo especificado."""
        domain = [('tipo_impuesto', '!=', False)]
        if tax_type:
            domain.append(('tipo_impuesto', '=', tax_type))
        return self.search(domain)

    def get_isv_taxes(self):
        """Obtiene impuestos ISV (15% y 18%)."""
        return self._get_fiscal_taxes('isv')

    def get_retention_taxes(self):
        """Obtiene impuestos de retención."""
        return self._get_fiscal_taxes('retencion')

    def get_exempt_taxes(self):
        """Obtiene impuestos exentos."""
        return self._get_fiscal_taxes('exento')

    def get_exonerated_taxes(self):
        """Obtiene impuestos exonerados."""
        return self._get_fiscal_taxes('exonerado')
