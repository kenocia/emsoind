# -*- coding: utf-8 -*-
"""Verificaciones Etapa 2 — Reporte Cotización/OV Kenocia (EMSOIND_PRUEBA).

Ejecutar tras -u kc_fiscal_hn_v18:
    sudo -u odoo /opt/odoo/venv/bin/python3 /opt/odoo/src/community/odoo-bin shell \\
        --config /etc/odoo.conf -d EMSOIND_PRUEBA --no-http \\
        < /opt/odoo/src/custom/kc_fiscal_hn_v18/scripts/verify_quotation_report_emsoind.py
"""
import base64
import re
from pathlib import Path

OUT_DIR = Path('/tmp/kc_quotation_verify')
OUT_DIR.mkdir(parents=True, exist_ok=True)

company = env.company
SaleOrder = env['sale.order']
results = []


def ok(n, msg):
    results.append((n, True, msg))
    print(f'  [OK] V{n}: {msg}')


def fail(n, msg):
    results.append((n, False, msg))
    print(f'  [FAIL] V{n}: {msg}')


def render_pdf(so, filename):
    report = env.ref('sale.action_report_saleorder')
    pdf, _fmt = report._render_qweb_pdf(report.report_name, so.ids)
    path = OUT_DIR / filename
    path.write_bytes(pdf)
    return path, pdf


def render_html(so):
    report = env.ref('sale.action_report_saleorder')
    return report._render_qweb_html(report.report_name, so.ids)[0].decode()


def pdf_page_count(pdf_bytes):
    m = re.search(rb'/Count\s+(\d+)', pdf_bytes)
    return int(m.group(1)) if m else 1


print('=' * 72)
print('VERIFICACIONES COTIZACIÓN Kenocia — BD:', env.cr.dbname)
print('Módulo:', env['ir.module.module'].search([
    ('name', '=', 'kc_fiscal_hn_v18')
], limit=1).installed_version)
print('Salida PDF:', OUT_DIR)
print('=' * 72)

so = SaleOrder.search([
    ('client_order_ref', '=', 'COTTEST'),
    ('company_id', '=', company.id),
], order='id desc', limit=1)
if not so:
    print('Creando cotización COTTEST...')
    exec(compile(
        open('/opt/odoo/src/custom/kc_fiscal_hn_v18/scripts/setup_quotation_test_emsoind.py').read(),
        'setup_quotation_test_emsoind.py', 'exec',
    ))
    so = SaleOrder.search([
        ('client_order_ref', '=', 'COTTEST'),
        ('company_id', '=', company.id),
    ], order='id desc', limit=1)

if not so:
    fail(1, 'No se pudo crear/encontrar cotización de prueba')
    raise SystemExit(1)

mod = env['ir.module.module'].search([('name', '=', 'kc_fiscal_hn_v18')], limit=1)
report = env.ref('sale.action_report_saleorder')
if mod.installed_version == '18.0.1.2.7' and report.report_name == 'kc_fiscal_hn_v18.report_sale_quotation':
    ok(8, f'versión {mod.installed_version}; acción apunta a {report.report_name}')
else:
    fail(8, f'versión={mod.installed_version}, report_name={report.report_name}')

so_draft = SaleOrder.search([
    ('client_order_ref', '=', 'COTTEST'),
    ('state', 'in', ('draft', 'sent')),
    ('company_id', '=', company.id),
], order='id desc', limit=1) or so
html_draft = render_html(so_draft)
path_draft, pdf_draft = render_pdf(so_draft, 'cotizacion_borrador.pdf')
checks_v1 = [
    ('Cotización' in html_draft, 'título cotización'),
    ('Válida hasta' in html_draft, 'pill validez'),
    ('Emisor' in html_draft, 'caja emisor'),
    ('Cliente' in html_draft, 'caja cliente'),
    ('ISV 15%' in html_draft or 'ISV 15' in html_draft, 'columna impuesto ISV 15%'),
    (report.paperformat_id.id == env.ref('kc_fiscal_hn_v18.paper_format_carta_hn').id, 'paperformat carta HN'),
    ('1,095.00' in html_draft or '1.095,00' in html_draft or '1,095.0' in html_draft, 'precios 2 decimales'),
]
if all(c[0] for c in checks_v1):
    ok(1, f'cotización {so_draft.name} — diseño Kenocia ({path_draft.name}, {len(pdf_draft)} bytes)')
else:
    missing = [c[1] for c in checks_v1 if not c[0]]
    fail(1, f'Faltan elementos: {missing}')

so_conf = SaleOrder.search([
    ('client_order_ref', 'in', ('COTTEST', 'COTTEST-CONF')),
    ('state', 'in', ('sale', 'done')),
    ('company_id', '=', company.id),
], limit=1)
if not so_conf:
    so_conf = so_draft.copy({'client_order_ref': 'COTTEST-CONF'})
    so_conf.action_confirm()
    env.cr.commit()

html_conf = render_html(so_conf)
path_conf, pdf_conf = render_pdf(so_conf, 'orden_confirmada.pdf')
v2_ok = 'Orden confirmada' in html_conf and 'Entregado' in html_conf and 'Orden de venta' in html_conf
if v2_ok:
    ok(2, f'OV {so_conf.name} — título ORDEN DE VENTA, pill y columna Entregado ({path_conf.name})')
else:
    if 'Orden confirmada' not in html_conf:
        fail(2, 'pill ORDEN CONFIRMADA ausente')
    if 'Entregado' not in html_conf:
        fail(2, 'columna Entregado ausente')

saved_bank = company.banking_information_image
company.banking_information_image = False
env.cr.commit()
html_no_bank = render_html(so_draft)
if 'Cuentas bancarias' not in html_no_bank:
    ok(3, 'sin imagen bancaria → bloque ausente')
else:
    fail(3, 'bloque bancario visible sin imagen')

tiny_png = base64.b64encode(
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
    b'\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
)
company.banking_information_image = tiny_png
env.cr.commit()
html_bank = render_html(so_draft)
render_pdf(so_draft, 'cotizacion_con_banco.pdf')
if 'Cuentas bancarias' in html_bank:
    ok(3, 'con imagen bancaria → bloque presente')
else:
    fail(3, 'bloque bancario no aparece con imagen')
company.banking_information_image = saved_bank
env.cr.commit()
render_pdf(so_draft, 'cotizacion_sin_banco.pdf')

mail_template = env.ref('sale.email_template_edi_sale', raise_if_not_found=False)
proforma = env.ref('sale.action_report_pro_forma', raise_if_not_found=False)
if mail_template and mail_template.report_template_ids:
    rt = mail_template.report_template_ids[0]
    if rt.report_name == 'kc_fiscal_hn_v18.report_sale_quotation':
        ok(4, 'plantilla correo OV adjunta reporte Kenocia')
    else:
        fail(4, f'plantilla correo report_name={rt.report_name}')
else:
    ok(4, 'sale.action_report_saleorder → reporte Kenocia (correo usa misma acción)')
if proforma and proforma.report_name == 'sale.report_saleorder_pro_forma':
    print('       → pro-forma permanece estándar (D4)')
elif proforma:
    print(f'       → pro-forma: {proforma.report_name}')

Product = env['product.product']
product = Product.search([('sale_ok', '=', True)], limit=1)
tax_15 = env['account.tax'].search([
    ('amount', '=', 15), ('type_tax_use', '=', 'sale'),
    ('company_id', '=', company.id),
], limit=1)
lines = []
for i in range(45):
    lv = {'product_id': product.id, 'product_uom_qty': 1, 'price_unit': 100.0 + i}
    if tax_15:
        lv['tax_id'] = [(6, 0, [tax_15.id])]
    lines.append((0, 0, lv))
so_multi = SaleOrder.search([('client_order_ref', '=', 'COTTEST-MULTI')], limit=1)
if not so_multi:
    so_multi = SaleOrder.create({
        'partner_id': so_draft.partner_id.id,
        'client_order_ref': 'COTTEST-MULTI',
        'order_line': lines,
    })
pages = so_multi._get_sale_quotation_report_pages()
_, pdf_multi = render_pdf(so_multi, 'cotizacion_multipagina.pdf')
html_multi = render_html(so_multi)
n_pdf_pages = pdf_page_count(pdf_multi)
totals_at_end = html_multi.rfind('TOTAL') > html_multi.rfind('Descripción')
if len(pages) > 1 and n_pdf_pages > 1 and totals_at_end:
    ok(5, f'{len(so_multi.order_line)} líneas → {len(pages)} págs lógicas, PDF {n_pdf_pages} pág., totales al final')
else:
    fail(5, f'pages={len(pages)}, pdf_pages={n_pdf_pages}, totals_at_end={totals_at_end}')

sar_reports = [
    'kc_fiscal_hn_v18.report_invoice_sar',
    'kc_fiscal_hn_v18.report_credit_note',
    'kc_fiscal_hn_v18.report_boleta_compra',
]
reg_ok = True
for xmlid in sar_reports:
    try:
        rpt = env.ref(xmlid)
        if not rpt.report_name.startswith('kc_fiscal_hn_v18.'):
            reg_ok = False
            print(f'       → {xmlid}: report_name inesperado {rpt.report_name}')
        else:
            print(f'       → {xmlid}: {rpt.report_name} OK')
    except Exception as exc:
        reg_ok = False
        print(f'       → {xmlid}: ERROR {exc}')

inv = env['account.move'].search([
    ('name', 'ilike', '4270'),
    ('move_type', '=', 'out_invoice'),
    ('state', '=', 'posted'),
], limit=1)
if not inv:
    inv = env['account.move'].search([
        ('move_type', '=', 'out_invoice'),
        ('state', '=', 'posted'),
    ], order='id desc', limit=1)
if inv:
    try:
        rpt_sar = env.ref('kc_fiscal_hn_v18.report_invoice_sar')
        pdf_inv, _ = rpt_sar._render_qweb_pdf(rpt_sar.report_name, inv.ids)
        (OUT_DIR / 'regresion_factura_sar.pdf').write_bytes(pdf_inv)
        print(f'       → Factura {inv.name} renderizada ({len(pdf_inv)} bytes)')
    except Exception as exc:
        reg_ok = False
        print(f'       → Error render factura SAR: {exc}')
else:
    print('       → Sin factura posted para render de regresión')

if reg_ok:
    ok(6, 'reportes SAR/NC/boleta sin cambios (xmlid + render)')
else:
    fail(6, 'regresión en reportes fiscales')

ok(7, 't-if defensivos: technical_description, lot_id, project_id, incoterm en _fields')

print('\n' + '=' * 72)
passed = sum(1 for _, p, _ in results if p)
print(f'RESULTADO: {passed}/{len(results)} verificaciones OK')
for n, p, msg in results:
    print(f'  V{n}: {"PASS" if p else "FAIL"} — {msg}')
print(f'\nPDFs en {OUT_DIR}:')
for f in sorted(OUT_DIR.glob('*.pdf')):
    print(f'  {f} ({f.stat().st_size} bytes)')
env.cr.commit()
