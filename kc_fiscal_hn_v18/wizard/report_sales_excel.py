# -*- coding: utf-8 -*-

import base64
import datetime
import io
import logging

import xlsxwriter
from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ReportSalesList(models.TransientModel):
    _name = 'kc_fiscal_hn.wizard.sales'
    _description = 'Reporte Ventas Netas'

    company_id = fields.Many2one('res.company', 'Company', required=True,
                                 default=lambda s: s.env.company.id, index=True)
    fecha_desde = fields.Date(string="Fecha Desde", default=datetime.date.today(), required=True)
    fecha_hasta = fields.Date(string="Fecha Hasta", default=datetime.date.today(), required=True)
    state = fields.Selection(selection=[('draft', 'Borrador'),
                                        ('posted', 'Posteado'),
                                        ('cancel', 'Cancelado'), ], string='Status', default='posted')

    def print_report(self):
        invoice = self.get_invoice()
        invoice_product = self.get_invoice_product()
        details_product = self.get_details_product()
        summary = self.get_summary()
        city_product = self.get_city_product()
        filename = 'Ventas Netas de ' + str(self.fecha_desde) + ' a ' + str(self.fecha_hasta) + '.xlsx'
        stream = io.BytesIO()
        workbook = xlsxwriter.Workbook(stream, {'in_memory': True})
        encabezado = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'left'})
        titulos = workbook.add_format({'bold': True, 'align': 'center'})
        subtitulos = workbook.add_format({'bold': True, 'align': 'center', 'text_wrap': True})
        subtitulos_largo = workbook.add_format({'bold': True, 'align': 'center', 'text_wrap': True})
        detalle = workbook.add_format({})
        detalle_moneda = workbook.add_format({'num_format': 'L#,##0.00'})
        detalle_porcentaje = workbook.add_format({'num_format': '0.00%'})

        sheet = workbook.add_worksheet('Vendedor - Ciudad')
        sheet2 = workbook.add_worksheet('Vendedor - Producto')
        sheet3 = workbook.add_worksheet('Venta Producto')
        sheet4 = workbook.add_worksheet('Venta Producto Resumen')
        sheet5 = workbook.add_worksheet('Venta Producto Resumen - Depart')
        # ENCABEZADO
        # sheet.write_merge(fila inicial, fila final, columna inicial, columna final)
        # --------------------------- HOJA 1 ---------------------
        sheet.merge_range(0, 0, 0, 3, 'GRUPO RIO S. DE R.L.', encabezado)
        sheet.merge_range(1, 0, 1, 5, 'REPORTE DE VENTAS NETAS DE ' + str(self.fecha_desde) + ' a ' + str(self.fecha_hasta), encabezado)
        sheet.merge_range(2, 0, 2, 3, 'VENDEDOR - DEPARTAMENTO', encabezado)

        # --------------------------- HOJA 2  ---------------------
        sheet2.merge_range(0, 0, 0, 3, 'GRUPO RIO S. DE R.L.', encabezado)
        sheet2.merge_range(1, 0, 1, 5, 'REPORTE DE VENTAS NETAS DE ' + str(self.fecha_desde) + ' a ' + str(self.fecha_hasta), encabezado)
        sheet2.merge_range(2, 0, 2, 3, 'VENDEDOR - PRODUCTO', encabezado)

        # --------------------------- HOJA 3  ---------------------
        sheet3.merge_range(0, 0, 0, 3, 'GRUPO RIO S. DE R.L.', encabezado)
        sheet3.merge_range(1, 0, 1, 5, 'REPORTE DE VENTAS NETAS DE ' + str(self.fecha_desde) + ' a ' + str(self.fecha_hasta), encabezado)
        sheet3.merge_range(2, 0, 2, 3, 'VENTA DETALLADA POR PRODUCTO', encabezado)

        # --------------------------- HOJA 4  ---------------------
        sheet4.merge_range(0, 0, 0, 3, 'GRUPO RIO S. DE R.L.', encabezado)
        sheet4.merge_range(1, 0, 1, 5, 'REPORTE DE VENTAS NETAS DE ' + str(self.fecha_desde) + ' a ' + str(self.fecha_hasta), encabezado)
        sheet4.merge_range(2, 0, 2, 3, 'VENTA PRODUCTO RESUMEN', encabezado)

        # --------------------------- HOJA 5  ---------------------
        sheet5.merge_range(0, 0, 0, 3, 'GRUPO RIO S. DE R.L.', encabezado)
        sheet5.merge_range(1, 0, 1, 5, 'REPORTE DE VENTAS NETAS DE ' + str(self.fecha_desde) + ' a ' + str(self.fecha_hasta), encabezado)
        sheet5.merge_range(2, 0, 2, 4, 'VENTA RESUMEN POR CIUDAD - PRODUCTO - LOTE', encabezado)
        # TITULOS
        # sheet.write(fila, columnas, texto, estilo)
        # --------------------------- HOJA 1 ---------------------
        sheet.write(5, 0, 'FECHA', subtitulos)
        sheet.write(5, 1, 'DOCUMENTO', subtitulos)
        # sheet.write(5, 2, 'BATCH N°', subtitulos)
        # sheet.write(5, 3, 'VENCIMIENTO', subtitulos)
        sheet.write(5, 2, 'CLIENTE', subtitulos)
        sheet.write(5, 3, 'PRODUCTO', subtitulos)
        sheet.write(5, 4, 'CTDAD', subtitulos)
        sheet.write(5, 5, 'VALOR ANTES DE ISV (VENTA BRUTA - DESCUENTOS)', subtitulos)
        print1 = self.write_sheet1(sheet, invoice, subtitulos, detalle, detalle_moneda)

        # --------------------------- HOJA 2  ---------------------
        sheet2.write(5, 0, 'FECHA', subtitulos)
        sheet2.write(5, 1, 'DOCUMENTO', subtitulos)
        # sheet2.write(5, 2, 'BATCH N°', subtitulos)
        # sheet2.write(5, 3, 'VENCIMIENTO', subtitulos)
        sheet2.write(5, 2, 'CLIENTE', subtitulos)
        sheet2.write(5, 3, 'PRODUCTO', subtitulos)
        sheet2.write(5, 4, 'CTDAD', subtitulos)
        sheet2.write(5, 5, 'VALOR ANTES DE ISV (VENTA BRUTA - DESCUENTOS)', subtitulos)
        print2 = self.write_sheet2(sheet2, invoice_product, subtitulos, detalle, detalle_moneda)

        # --------------------------- HOJA 3  ---------------------
        sheet3.write(5, 0, 'FECHA', subtitulos)
        sheet3.write(5, 1, 'DOCUMENTO', subtitulos)
        # sheet3.write(5, 2, 'BATCH N°', subtitulos)
        # sheet3.write(5, 3, 'VENCIMIENTO', subtitulos)
        sheet3.write(5, 2, 'CLIENTE', subtitulos)
        sheet3.write(5, 3, 'PRODUCTO', subtitulos)
        sheet3.write(5, 4, 'CTDAD', subtitulos)
        sheet3.write(5, 5, 'VALOR ANTES DE ISV (VENTA BRUTA - DESCUENTOS)', subtitulos)
        print3 = self.write_sheet3(sheet3, details_product, subtitulos, detalle, detalle_moneda)

        # --------------------------- HOJA 4  ---------------------
        # sheet4.write(5, 0, 'BATCH N°', subtitulos)
        # sheet4.write(5, 1, 'VENCIMIENTO', subtitulos)
        sheet4.write(5, 0, 'PRODUCTO', subtitulos)
        sheet4.write(5, 1, 'CTDAD', subtitulos)
        sheet4.write(5, 2, 'VALOR ANTES DE ISV (VENTA BRUTA - DESCUENTOS)', subtitulos)
        print4 = self.write_sheet4(sheet4, summary, subtitulos, detalle, detalle_moneda)

        # --------------------------- HOJA 5  ---------------------
        # sheet5.write(5, 0, 'BATCH N°', subtitulos)
        # sheet5.write(5, 1, 'VENCIMIENTO', subtitulos)
        sheet5.write(5, 0, 'PRODUCTO', subtitulos)
        sheet5.write(5, 1, 'CTDAD', subtitulos)
        sheet5.write(5, 2, 'VALOR ANTES DE ISV (VENTA BRUTA - DESCUENTOS)', subtitulos)
        print5 = self.write_sheet5(sheet5, city_product, subtitulos, detalle, detalle_moneda)

        workbook.close()
        fp = stream
        export_id = self.env['kc_fiscal_hn.sales.excel'].create(
            {'excel_file': base64.b64encode(fp.getvalue()), 'file_name': filename})
        fp.close()
        return {
            'view_mode': 'form',
            'res_id': export_id.id,
            'res_model': 'kc_fiscal_hn.sales.excel',
            'view_type': 'form',
            'type': 'ir.actions.act_window',
            'target': 'new'
        }
        return True

    def get_invoice(self):
        domain = ''
        domain = [('company_id', '=', self.company_id.id),
                  ('invoice_date', '>=', self.fecha_desde),
                  ('invoice_date', '<=', self.fecha_hasta),
                  ('product_id', '!=', False),
                  # ('product_id.name', '!=', 'Descuento'),
                  ('display_type', '=', 'product'),
                  ('parent_state', '=', self.state),
                  ('move_type', '=', 'out_invoice')]

        invoices = self.env['account.move.line'].search(domain)
        # Diccionario para agrupar por vendedor y ciudad del cliente
        grouped_data = {}

        for invoice in invoices:
            # Obtener vendedor y ciudad del cliente
            seller = invoice.move_id.invoice_user_id
            city = invoice.move_id.depto.name  # Asumiendo que 'depto' es un campo en el modelo res.partner

            # Clave del diccionario
            key = (seller.id, city)
            if key not in grouped_data:
                grouped_data[key] = []

            # Obtener los detalles requeridos
            invoice_date = invoice.move_id.invoice_date.strftime('%d-%m-%Y') if invoice.move_id.invoice_date else ''
            invoice_number = invoice.move_id.name
            # lot_number = invoice.serial_no.name if invoice.serial_no else ''
            # lot_expiry_date = invoice.serial_no.expiration_date.strftime('%d-%m-%Y') if invoice.serial_no and invoice.serial_no.expiration_date else ''
            customer = invoice.move_id.partner_id.name
            product = invoice.product_id.name
            quantity = invoice.quantity
            value_before_tax = invoice.price_subtotal

            grouped_data[key].append({
                'invoice_date': invoice_date,
                'invoice_number': invoice_number,
                # 'lot_number': lot_number,
                # 'lot_expiry_date': lot_expiry_date,
                'customer': customer,
                'product': product,
                'quantity': quantity,
                'value_before_tax': value_before_tax,
            })

            # Si necesitas transformar el diccionario en una lista de datos
        data = []
        for (seller_id, city), invoices in grouped_data.items():
            seller_name = self.env['res.users'].browse(seller_id).name
            data.append({
                'seller': seller_name if seller_name else '',
                'city': city,
                'invoices': invoices
            })
        sorted_data = sorted(data, key=lambda x: x['seller'])

        return sorted_data

    def get_invoice_product(self):
        domain = ''
        domain = [('company_id', '=', self.company_id.id),
                  ('invoice_date', '>=', self.fecha_desde),
                  ('invoice_date', '<=', self.fecha_hasta),
                  ('product_id', '!=', False),
                  # ('product_id.name', '!=', 'Descuento'),
                  ('display_type', '=', 'product'),
                  ('parent_state', '=', self.state),
                  ('move_type', '=', 'out_invoice')]

        invoices = self.env['account.move.line'].search(domain)
        # Diccionario para agrupar por vendedor y ciudad del cliente
        grouped_data = {}

        for invoice in invoices:
            # Obtener vendedor y ciudad del cliente
            seller = invoice.move_id.invoice_user_id

            # Clave del diccionario
            key = seller.id
            if key not in grouped_data:
                grouped_data[key] = []

            # Obtener los detalles requeridos
            invoice_date = invoice.move_id.invoice_date.strftime('%d-%m-%Y') if invoice.move_id.invoice_date else ''
            invoice_number = invoice.move_id.name
            # lot_number = invoice.serial_no.name if invoice.serial_no else ''
            # lot_expiry_date = invoice.serial_no.expiration_date.strftime('%d-%m-%Y') if invoice.serial_no and invoice.serial_no.expiration_date else ''
            customer = invoice.move_id.partner_id.name
            product = invoice.product_id.name
            quantity = invoice.quantity
            value_before_tax = invoice.price_subtotal

            grouped_data[key].append({
                'invoice_date': invoice_date,
                'invoice_number': invoice_number,
                # 'lot_number': lot_number,
                # 'lot_expiry_date': lot_expiry_date,
                'customer': customer,
                'product': product,
                'quantity': quantity,
                'value_before_tax': value_before_tax,
            })

            # Si necesitas transformar el diccionario en una lista de datos
        data = []
        for seller_id, invoices in grouped_data.items():
            seller_name = self.env['res.users'].browse(seller_id).name
            data.append({
                'seller': seller_name,
                'invoices': invoices
            })
        sorted_data = sorted(data, key=lambda x: x['seller'])

        return sorted_data

    def get_details_product(self):
        domain = ''
        domain = [('company_id', '=', self.company_id.id),
                  ('invoice_date', '>=', self.fecha_desde),
                  ('invoice_date', '<=', self.fecha_hasta),
                  ('product_id', '!=', False),
                  # ('product_id.name', '!=', 'Descuento'),
                  ('display_type', '=', 'product'),
                  ('parent_state', '=', self.state),
                  ('move_type', '=', 'out_invoice')]

        invoices = self.env['account.move.line'].search(domain)
        # Diccionario para agrupar por vendedor y ciudad del cliente
        grouped_data = {}

        for invoice in invoices:
            # Obtener vendedor y ciudad del cliente
            product = invoice.product_id

            # Clave del diccionario
            key = product.id
            if key not in grouped_data:
                grouped_data[key] = []

            # Obtener los detalles requeridos
            invoice_date = invoice.move_id.invoice_date.strftime('%d-%m-%Y') if invoice.move_id.invoice_date else ''
            invoice_number = invoice.move_id.name
            # lot_number = invoice.serial_no.name if invoice.serial_no else ''
            # lot_expiry_date = invoice.serial_no.expiration_date.strftime('%d-%m-%Y') if invoice.serial_no and invoice.serial_no.expiration_date else ''
            customer = invoice.move_id.partner_id.name
            producto = invoice.product_id.name
            quantity = invoice.quantity
            value_before_tax = invoice.price_subtotal

            grouped_data[key].append({
                'invoice_date': invoice_date,
                'invoice_number': invoice_number,
                # 'lot_number': lot_number,
                # 'lot_expiry_date': lot_expiry_date,
                'customer': customer,
                'product': producto,
                'quantity': quantity,
                'value_before_tax': value_before_tax,
            })

            # Si necesitas transformar el diccionario en una lista de datos
        data = []
        for product_id, invoices in grouped_data.items():
            product_name = self.env['product.product'].browse(product_id).name
            data.append({
                'product': product_name,
                'invoices': invoices
            })
        sorted_data = sorted(data, key=lambda x: x['product'])

        return sorted_data

    def get_summary(self):
        domain = ''
        domain = [('company_id', '=', self.company_id.id),
                  ('invoice_date', '>=', self.fecha_desde),
                  ('invoice_date', '<=', self.fecha_hasta),
                  ('product_id', '!=', False),
                  # ('product_id.name', '!=', 'Descuento'),
                  ('display_type', '=', 'product'),
                  ('parent_state', '=', self.state),
                  ('move_type', '=', 'out_invoice')]

        invoices = self.env['account.move.line'].search(domain)
        # Diccionario para agrupar por vendedor y ciudad del cliente
        grouped_data = {}

        for invoice in invoices:
            # Obtener vendedor y ciudad del cliente
            product = invoice.product_id

            # Clave del diccionario
            key = product.id
            if key not in grouped_data:
                grouped_data[key] = {
                    'product': product.name,
                    # 'lot_number': invoice.serial_no.name if invoice.serial_no else '',
                    # 'lot_expiry_date': invoice.serial_no.expiration_date.strftime('%d-%m-%Y') if invoice.serial_no and invoice.serial_no.expiration_date else '',
                    'quantity': 0,
                    'value_before_tax': 0,
                }
            grouped_data[key]['quantity'] += invoice.quantity
            grouped_data[key]['value_before_tax'] += invoice.price_subtotal

        # Obtener los detalles requeridos
        # Transformar el diccionario en una lista de datos
        data = list(grouped_data.values())

        # Ordenar los datos por producto y luego por lote
        sorted_data = sorted(data, key=lambda x: (x['product']))

        return sorted_data

    def get_city_product(self):
        domain = ''
        domain = [('company_id', '=', self.company_id.id),
                  ('invoice_date', '>=', self.fecha_desde),
                  ('invoice_date', '<=', self.fecha_hasta),
                  ('product_id', '!=', False),
                  # ('product_id.name', '!=', 'Descuento'),
                  ('display_type', '=', 'product'),
                  ('parent_state', '=', self.state),
                  ('move_type', '=', 'out_invoice')]

        invoices = self.env['account.move.line'].search(domain)
        # Diccionario para agrupar por vendedor y ciudad del cliente
        grouped_data = {}

        for invoice in invoices:
            # Obtener vendedor y ciudad del cliente
            product = invoice.product_id
            city = invoice.move_id.depto.name or 'Sin ciudad'

            # Clave del diccionario
            key = city
            if key not in grouped_data:
                grouped_data[key] = []

            # lot_number = invoice.serial_no.name if invoice.serial_no else ''
            # lot_expiry_date = invoice.serial_no.expiration_date.strftime('%d-%m-%Y') if invoice.serial_no and invoice.serial_no.expiration_date else ''
            product = invoice.product_id.name
            quantity = invoice.quantity
            value_before_tax = invoice.price_subtotal

            grouped_data[key].append({
                # 'lot_number': lot_number,
                # 'lot_expiry_date': lot_expiry_date,
                'product': product,
                'quantity': quantity,
                'value_before_tax': value_before_tax,
            })

            # Si necesitas transformar el diccionario en una lista de datos
        data = []
        for city, invoices in grouped_data.items():
            data.append({
                'city': city,
                'invoices': invoices
            })
        sorted_data = sorted(data, key=lambda x: x['city'])

        return sorted_data

    def write_sheet1(self, sheet, invoice, subtitulos, detalle, detalle_moneda):
        curren_seller = None
        total_seller = 0
        total_general = 0
        f = 6
        for i in invoice:
            total_value = 0
            if curren_seller == None:
                curren_seller = str(i['seller'])
            elif curren_seller != str(i['seller']):
                sheet.write(f, 4, 'TOTAL VENDEDOR', detalle)
                sheet.write(f, 5, total_seller, detalle_moneda)
                f += 2
                total_seller = 0
                curren_seller = str(i['seller'])

            sheet.merge_range(f, 0, f, 3, str(i['seller']) + ' / ' + str(i['city']), subtitulos)
            f += 1
            for line in i['invoices']:
                sheet.write(f, 0, line['invoice_date'], detalle)
                sheet.write(f, 1, line['invoice_number'], detalle)
                # sheet.write(f, 2, str(line['lot_number']), detalle)
                # sheet.write(f, 3, line['lot_expiry_date'], detalle)
                sheet.write(f, 2, line['customer'], detalle)
                sheet.write(f, 3, line['product'], detalle)
                sheet.write(f, 4, line['quantity'], detalle)
                sheet.write(f, 5, line['value_before_tax'], detalle_moneda)
                total_value += line['value_before_tax']
                f += 1
            sheet.write(f, 4, 'TOTAL DETALLE', detalle)
            sheet.write(f, 5, total_value, detalle_moneda)
            f += 2
            total_seller += total_value
            total_general += total_value
        sheet.write(f, 4, 'TOTAL GENERAL', detalle)
        sheet.write(f, 5, total_general, detalle_moneda)

    def write_sheet2(self, sheet, invoice, subtitulos, detalle, detalle_moneda):
        total_seller = 0
        total_general = 0
        f = 6
        for i in invoice:
            total_seller = 0
            sheet.merge_range(f, 0, f, 3, str(i['seller']), subtitulos)
            f += 1
            for line in i['invoices']:
                sheet.write(f, 0, line['invoice_date'], detalle)
                sheet.write(f, 1, line['invoice_number'], detalle)
                # sheet.write(f, 2, str(line['lot_number']), detalle)
                # sheet.write(f, 3, line['lot_expiry_date'], detalle)
                sheet.write(f, 2, line['customer'], detalle)
                sheet.write(f, 3, line['product'], detalle)
                sheet.write(f, 4, line['quantity'], detalle)
                sheet.write(f, 5, line['value_before_tax'], detalle_moneda)
                total_seller += line['value_before_tax']
                total_general += line['value_before_tax']
                f += 1
            sheet.write(f, 4, 'TOTAL VENDEDOR', detalle)
            sheet.write(f, 5, total_seller, detalle_moneda)
            f += 2
        sheet.write(f, 4, 'TOTAL GENERAL', detalle)
        sheet.write(f, 5, total_general, detalle_moneda)

    def write_sheet3(self, sheet, invoice, subtitulos, detalle, detalle_moneda):
        total_seller = 0
        total_general = 0
        f = 6
        for i in invoice:
            total_seller = 0
            sheet.merge_range(f, 0, f, 3, str(i['product']), subtitulos)
            f += 1
            for line in i['invoices']:
                sheet.write(f, 0, line['invoice_date'], detalle)
                sheet.write(f, 1, line['invoice_number'], detalle)
                # sheet.write(f, 2, str(line['lot_number']), detalle)
                # sheet.write(f, 3, line['lot_expiry_date'], detalle)
                sheet.write(f, 2, line['customer'], detalle)
                sheet.write(f, 3, line['product'], detalle)
                sheet.write(f, 4, line['quantity'], detalle)
                sheet.write(f, 5, line['value_before_tax'], detalle_moneda)
                total_seller += line['value_before_tax']
                total_general += line['value_before_tax']
                f += 1
            sheet.write(f, 4, 'TOTAL PRODUCTO', detalle)
            sheet.write(f, 5, total_seller, detalle_moneda)
            f += 2
        sheet.write(f, 4, 'TOTAL GENERAL', detalle)
        sheet.write(f, 5, total_general, detalle_moneda)

    def write_sheet4(self, sheet, invoice, subtitulos, detalle, detalle_moneda):
        total_seller = 0
        f = 6
        for line in invoice:
            # sheet.write(f, 0, str(line['lot_number']), detalle)
            # sheet.write(f, 1, line['lot_expiry_date'], detalle)
            sheet.write(f, 0, line['product'], detalle)
            sheet.write(f, 1, line['quantity'], detalle)
            sheet.write(f, 2, line['value_before_tax'], detalle_moneda)
            total_seller += line['value_before_tax']
            f += 1
        sheet.write(f, 1, 'TOTAL GENERAL', detalle)
        sheet.write(f, 2, total_seller, detalle_moneda)

    def write_sheet5(self, sheet, invoice, subtitulos, detalle, detalle_moneda):
        total_seller = 0
        total = 0
        f = 6
        for i in invoice:
            total_seller = 0
            sheet.merge_range(f, 0, f, 3, str(i['city']), subtitulos)
            f += 1
            for line in i['invoices']:
                # sheet.write(f, 0, str(line['lot_number']), detalle)
                # sheet.write(f, 1, line['lot_expiry_date'], detalle)
                sheet.write(f, 0, line['product'], detalle)
                sheet.write(f, 1, line['quantity'], detalle)
                sheet.write(f, 2, line['value_before_tax'], detalle_moneda)
                total_seller += line['value_before_tax']
                f += 1
            sheet.write(f, 1, 'TOTAL PRODUCTO', detalle)
            sheet.write(f, 2, total_seller, detalle_moneda)
            total += total_seller
            f += 1
        sheet.write(f, 1, 'TOTAL GENERAL', detalle)
        sheet.write(f, 2, total, detalle_moneda)
 

class ReportSalesExcel(models.TransientModel):
    _name = "kc_fiscal_hn.sales.excel"
    _description = "Reporte Ventas Excel"

    excel_file = fields.Binary('Lista Factura', readonly=True)
    file_name = fields.Char('Excel File', size=64)
