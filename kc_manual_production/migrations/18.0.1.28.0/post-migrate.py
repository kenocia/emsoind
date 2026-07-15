# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Activa producción simple en GENROTULOS (TEST / bases con ese código)."""
    cr.execute("""
        UPDATE product_template
           SET kc_simple_production = TRUE,
               kc_invoice_detail_mode = 'product_only'
         WHERE id IN (
            SELECT DISTINCT pp.product_tmpl_id
              FROM product_product pp
             WHERE pp.default_code = 'GENROTULOS'
                OR pp.default_code ILIKE 'GENROTULO%'
         )
           AND COALESCE(kc_simple_production, FALSE) IS NOT TRUE
    """)
    _logger.info(
        "kc_manual_production: producción simple activada en %s ficha(s) GENROTULOS.",
        cr.rowcount,
    )
