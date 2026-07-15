# -*- coding: utf-8 -*-

from odoo import _, api, models
from odoo.exceptions import UserError


class FiscalBookLineMixin(models.AbstractModel):
    """Impide edición manual de líneas generadas desde facturas."""

    _name = 'kc.fiscal.book.line.mixin'
    _description = 'Mixin líneas de libros SAR (solo lectura)'

    def write(self, vals):
        if not self.env.context.get('skip_book_line_lock'):
            raise UserError(_(
                'Las líneas del libro no se pueden modificar '
                'manualmente.\n\n'
                'Use el botón «Generar Libro» para actualizar '
                'desde las facturas confirmadas.',
            ))
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get('skip_book_line_lock'):
            raise UserError(_(
                'Las líneas del libro no se pueden eliminar '
                'manualmente.\n\n'
                'Regenera el libro para actualizar el contenido.',
            ))
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('skip_book_line_lock'):
            raise UserError(_(
                'Las líneas del libro se crean automáticamente '
                'al pulsar «Generar Libro».',
            ))
        return super().create(vals_list)
