# -*- coding: utf-8 -*-

from odoo.fields import Command


def _emsoind_configure_categories(env):
    """Alinea etiquetas existentes EMSOIND con los flags de control."""
    Category = env['res.partner.category'].sudo()
    IrModelData = env['ir.model.data'].sudo()
    specs = [
        (
            'partner_category_cliente', 'Cliente',
            {'use_in_sales': True, 'require_sales_fields': True},
        ),
        (
            'partner_category_proveedor', 'Proveedor',
            {'use_in_purchases': True},
        ),
        (
            'partner_category_cliente_proveedor', 'Cliente / Proveedor',
            {
                'use_in_sales': True,
                'use_in_purchases': True,
                'require_sales_fields': True,
            },
        ),
    ]
    for xml_suffix, name, vals in specs:
        xmlid = f'emsoind_sale.{xml_suffix}'
        tag = env.ref(xmlid, raise_if_not_found=False)
        if not tag:
            tag = Category.search([('name', '=', name)], limit=1)
        if not tag:
            tag = Category.create({'name': name, **vals})
        else:
            tag.write(vals)
        existing = IrModelData.search([
            ('module', '=', 'emsoind_sale'),
            ('name', '=', xml_suffix),
        ], limit=1)
        if existing:
            existing.write({'res_id': tag.id})
        else:
            IrModelData.create({
                'module': 'emsoind_sale',
                'name': xml_suffix,
                'model': 'res.partner.category',
                'res_id': tag.id,
                'noupdate': True,
            })


def _emsoind_cleanup_supplier_customer_rank(env):
    """Proveedores sin etiqueta de venta no deben colarse por customer_rank."""
    partners = env['res.partner'].sudo().search([
        ('emsoind_use_in_purchases', '=', True),
        ('emsoind_use_in_sales', '=', False),
        ('customer_rank', '>', 0),
    ])
    if partners:
        partners.with_context(emsoind_skip_sales_validation=True).write({
            'customer_rank': 0,
        })


def _emsoind_init_config_parameters(env):
    """Valor por defecto solo en instalaciones nuevas (sin pisar Ajustes)."""
    icp = env['ir.config_parameter'].sudo()
    if not icp._get_param('emsoind_sale.auto_section_by_category'):
        icp.set_param('emsoind_sale.auto_section_by_category', 'True')


def post_init_hook(env):
    """Etiqueta contactos existentes según customer_rank / supplier_rank."""
    _emsoind_configure_categories(env)
    _emsoind_init_config_parameters(env)
    Partner = env['res.partner'].sudo()
    cliente = env.ref('emsoind_sale.partner_category_cliente', raise_if_not_found=False)
    proveedor = env.ref('emsoind_sale.partner_category_proveedor', raise_if_not_found=False)
    if not cliente and not proveedor:
        return

    if cliente:
        for partner in Partner.search([
            ('customer_rank', '>', 0),
            ('category_id', 'not in', cliente.ids),
        ]):
            partner.with_context(emsoind_skip_sales_validation=True).write(
                {'category_id': [Command.link(cliente.id)]},
            )

    if proveedor:
        for partner in Partner.search([
            ('supplier_rank', '>', 0),
            ('category_id', 'not in', proveedor.ids),
        ]):
            partner.with_context(emsoind_skip_sales_validation=True).write(
                {'category_id': [Command.link(proveedor.id)]},
            )

    _emsoind_cleanup_supplier_customer_rank(env)
