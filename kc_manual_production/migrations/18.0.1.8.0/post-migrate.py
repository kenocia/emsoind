# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.kc_manual_production.hooks import _ensure_production_lines
    _ensure_production_lines(env)
