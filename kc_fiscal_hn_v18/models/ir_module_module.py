# -*- coding: utf-8 -*-

import sys

from odoo import models

_MODULE_NAME = 'kc_fiscal_hn_v18'
_MODULE_PREFIX = f'odoo.addons.{_MODULE_NAME}'


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def _button_immediate_function(self, function):
        if _MODULE_NAME in self.mapped('name'):
            self._reload_kc_fiscal_python_module()
        return super()._button_immediate_function(function)

    @staticmethod
    def _reload_kc_fiscal_python_module():
        """
        Odoo no recarga módulos Python ya presentes en sys.modules
        al actualizar desde la UI. Esto provoca KeyError cuando se
        agregan modelos nuevos (p. ej. kc_fiscal_hn.codigo.sar).
        """
        for name in list(sys.modules):
            if name == _MODULE_PREFIX or name.startswith(f'{_MODULE_PREFIX}.'):
                del sys.modules[name]
