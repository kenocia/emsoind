# -*- coding: utf-8 -*-
"""Utilidades compartidas para exportación Excel con xlsxwriter (Odoo 19 / Python 3.12)."""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from typing import Any

import xlsxwriter
from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def fiscal_workbook_styles(workbook: xlsxwriter.Workbook) -> dict[str, Any]:
    """Estilos estándar para reportes fiscales SAR."""
    return {
        'encabezado': workbook.add_format({
            'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter',
        }),
        'titulos': workbook.add_format({'bold': True, 'align': 'center'}),
        'subtitulos': workbook.add_format({'bold': True, 'align': 'center', 'text_wrap': True}),
        'detalle': workbook.add_format({}),
        'moneda': workbook.add_format({'num_format': 'L#,##0.00'}),
        'porcentaje': workbook.add_format({'num_format': '0.00%'}),
    }


def build_excel_attachment(
    env,
    *,
    filename: str,
    excel_model: str,
    build_callback,
) -> dict:
    """Genera un workbook en memoria y devuelve acción de ventana con el adjunto.

    :param build_callback: función(workbook, styles) que escribe las hojas.
    """
    try:
        stream = BytesIO()
        workbook = xlsxwriter.Workbook(stream, {'in_memory': True})
        styles = fiscal_workbook_styles(workbook)
        build_callback(workbook, styles)
        workbook.close()
        export = env[excel_model].create({
            'excel_file': base64.b64encode(stream.getvalue()),
            'file_name': filename,
        })
        stream.close()
        return {
            'type': 'ir.actions.act_window',
            'res_model': excel_model,
            'res_id': export.id,
            'view_mode': 'form',
            'target': 'new',
        }
    except Exception as exc:
        _logger.error('Error generando Excel %s: %s', filename, exc, exc_info=True)
        raise UserError(_('No se pudo generar el reporte Excel: %s') % exc) from exc
