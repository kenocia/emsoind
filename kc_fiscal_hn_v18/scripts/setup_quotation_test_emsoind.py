# -*- coding: utf-8 -*-
"""Cotización de prueba — Reporte comercial Kenocia en EMSOIND_PRUEBA.

Equivalente comercial a C-2607-00007 (3 líneas, ISV 15%, cliente con RTN).

Ejecutar:
    sudo -u odoo /opt/odoo/venv/bin/python3 /opt/odoo/src/community/odoo-bin shell \\
        --config /etc/odoo.conf -d EMSOIND_PRUEBA --no-http \\
        < /opt/odoo/src/custom/kc_fiscal_hn_v18/scripts/setup_quotation_test_emsoind.py
"""
from datetime import timedelta

from odoo import fields

MARKER = 'COTTEST'
company = env.company
SaleOrder = env['sale.order']
Partner = env['res.partner']
Product = env['product.product']
Tax = env['account.tax']

print('=' * 72)
print('COTIZACIÓN PRUEBA Kenocia — BD:', env.cr.dbname)
print('Empresa:', company.name)
print('=' * 72)

existing = SaleOrder.search([
    ('client_order_ref', '=', MARKER),
    ('company_id', '=', company.id),
], order='id desc', limit=1)
if existing:
    print(f'Ya existe OV de prueba: {existing.name} (state={existing.state})')
    print('Se reutiliza; elimine manualmente si desea recrear.')
    env.cr.commit()
    raise SystemExit(0)

partner = Partner.search([
    ('vat', '!=', False),
    ('is_company', '=', True),
    ('company_id', 'in', [False, company.id]),
], limit=1)
if not partner:
    partner = Partner.search([('customer_rank', '>', 0)], limit=1)
print('Cliente:', partner.name, '| RTN:', partner.vat or '—')

tax_15 = Tax.search([
    ('amount', '=', 15),
    ('type_tax_use', '=', 'sale'),
    ('company_id', '=', company.id),
], limit=1)
if not tax_15:
    tax_15 = Tax.search([
        ('type_tax_use', '=', 'sale'),
        ('company_id', '=', company.id),
    ], limit=1)
print('Impuesto venta:', tax_15.name if tax_15 else 'NINGUNO')

products = Product.search([
    ('sale_ok', '=', True),
    ('active', '=', True),
], limit=3)
if len(products) < 3:
    print('⚠️  Menos de 3 productos vendibles; se repiten los disponibles.')
    while len(products) < 3 and products:
        products |= products[0]
if not products:
    raise SystemExit('No hay productos vendibles en la BD.')

prices = [1095.0, 2500.0, 875.50]
qtys = [10.0, 5.0, 20.0]

line_vals = []
for idx, product in enumerate(products[:3]):
    vals = {
        'product_id': product.id,
        'product_uom_qty': qtys[idx],
        'price_unit': prices[idx],
    }
    if tax_15:
        vals['tax_id'] = [(6, 0, [tax_15.id])]
    if 'technical_description' in env['sale.order.line']._fields:
        vals['technical_description'] = (
            f'Especificación técnica de prueba línea {idx + 1} ({MARKER})'
        )
    line_vals.append((0, 0, vals))

payment_term = env['account.payment.term'].search([], limit=1)
user = env.user

so_vals = {
    'partner_id': partner.id,
    'client_order_ref': MARKER,
    'validity_date': fields.Date.today() + timedelta(days=30),
    'payment_term_id': payment_term.id if payment_term else False,
    'user_id': user.id,
    'order_line': line_vals,
    'note': 'Cotización de prueba — formato Kenocia Etapa 2.',
}
so = SaleOrder.create(so_vals)
print(f'\n✓ Cotización creada: {so.name}')
print(f'  Subtotal: {so.amount_untaxed:.2f} | Total: {so.amount_total:.2f}')
print(f'  Líneas: {len(so.order_line.filtered(lambda l: not l.display_type))}')
env.cr.commit()
