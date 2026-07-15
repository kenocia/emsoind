# -*- coding: utf-8 -*-
from odoo import fields, models


class StockMove(models.Model):
    """Vincula los movimientos generados por el módulo con su documento origen
    y propaga la distribución analítica del RP/CMP al motor de valoración.
    """
    _inherit = 'stock.move'

    kc_production_entry_id = fields.Many2one(
        comodel_name='kc.production.entry',
        string='Registro de Producción (KC)',
        readonly=True,
        index=True,
        copy=False,
    )
    kc_production_consumption_id = fields.Many2one(
        comodel_name='kc.production.consumption',
        string='Consumo de MP (KC)',
        readonly=True,
        index=True,
        copy=False,
    )

    def _get_analytic_distribution(self):
        """Devuelve la distribución analítica del documento origen (RP/CMP).

        Odoo aplica el signo automáticamente según la dirección del movimiento:
        salida (CMP) -> monto negativo (costo); entrada (RP) -> monto positivo.
        Si el movimiento no proviene de este módulo, usa el comportamiento estándar.
        """
        self.ensure_one()
        distribucion = (
            self.kc_production_entry_id.analytic_distribution
            or self.kc_production_consumption_id.analytic_distribution
        )
        if distribucion:
            return distribucion
        return super()._get_analytic_distribution()
