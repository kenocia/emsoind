# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# Líneas estándar por compañía (sin "General").
KC_PRODUCTION_LINES = (
    ('Linea Comercializacion', 'COM', 10),
    ('Linea Rotulacion', 'ROT', 20),
    ('Linea Metalmecanica', 'MET', 30),
)


def _ensure_production_lines(env):
    """Asegura las 3 líneas por compañía y reasigna RP huérfanos o en 'General'."""
    Line = env['kc.production.line']
    Entry = env['kc.production.entry']

    for company in env['res.company'].search([]):
        lines_by_name = {}
        for name, code, sequence in KC_PRODUCTION_LINES:
            line = Line.search([
                ('name', '=', name),
                ('company_id', '=', company.id),
            ], limit=1)
            if not line:
                line = Line.create({
                    'name': name,
                    'code': code,
                    'sequence': sequence,
                    'company_id': company.id,
                })
                _logger.info(
                    "Producción Manual KC: línea '%s' creada para %s.",
                    name, company.name,
                )
            lines_by_name[name] = line

        general = Line.search([
            ('name', '=', 'General'),
            ('company_id', '=', company.id),
        ], limit=1)
        fallback = lines_by_name.get('Linea Comercializacion')

        if general:
            rotulacion = lines_by_name.get('Linea Rotulacion') or fallback
            entries_on_general = Entry.with_context(active_test=False).search([
                ('company_id', '=', company.id),
                ('production_line_id', '=', general.id),
            ])
            if entries_on_general and rotulacion:
                entries_on_general.write({'production_line_id': rotulacion.id})
            general.unlink()
            _logger.info(
                "Producción Manual KC: línea 'General' eliminada en %s.",
                company.name,
            )

        orphans = Entry.with_context(active_test=False).search([
            ('company_id', '=', company.id),
            ('production_line_id', '=', False),
        ])
        if orphans and fallback:
            orphans.write({'production_line_id': fallback.id})
            _logger.info(
                "Producción Manual KC: %s RP(s) asignados a '%s' en %s.",
                len(orphans), fallback.name, company.name,
            )

        _map_production_line_categories(env, lines_by_name, company)


def _map_production_line_categories(env, lines_by_name, company):
    """Asigna categorías PT a cada línea (solo si aún no tienen categorías)."""
    Categ = env['product.category']
    mapping = {
        'Linea Rotulacion': 'PT / ROTULACION',
        'Linea Metalmecanica': 'PT / METALMECANICA',
        'Linea Comercializacion': 'PT',
    }
    for line_name, categ_path in mapping.items():
        line = lines_by_name.get(line_name)
        if not line or line.product_categ_ids:
            continue
        categ = Categ.search([('complete_name', '=', categ_path)], limit=1)
        if categ:
            line.product_categ_ids = [(6, 0, categ.ids)]
            _logger.info(
                "Producción Manual KC: línea '%s' → categoría '%s'.",
                line_name, categ_path,
            )


def post_init_hook(env):
    """Hook de instalación: tipos de operación y líneas de producción."""
    PickingType = env['stock.picking.type']
    for company in env['res.company'].search([]):
        for role in ('rp', 'cmp'):
            picking_type = PickingType._kc_get_or_create_production_type(role, company)
            if picking_type:
                _logger.info(
                    "Producción Manual KC: tipo de operación '%s' listo para %s (%s).",
                    role, company.name, picking_type.name,
                )
            else:
                _logger.warning(
                    "Producción Manual KC: no se pudo crear el tipo '%s' para %s "
                    "(¿falta almacén o ubicación de Producción?).",
                    role, company.name,
                )
    _ensure_production_lines(env)
