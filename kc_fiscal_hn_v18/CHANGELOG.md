# Changelog — kc_fiscal_hn_v18

## 18.0.1.2.7 — Etapa 2: Cotización / Orden de Venta Kenocia

- Nuevo reporte comercial `report_sale_quotation` (familia visual Factura SAR 2026):
  encabezado con pill de validez u orden confirmada, cajas emisor/cliente, barra de
  condiciones, tabla con `technical_description` y lote defensivos, totales con banda
  `#0c2d5e`, pie no fiscal y paginación multipágina (26/15 líneas).
- Sobrescritura de `sale.action_report_saleorder` vía registro XML (sin `inherit_id`).
- Helpers en `sale.order`: `_get_sale_quotation_report_pages`, `_get_sale_quotation_tax_rows`,
  `_sale_quotation_show_delivered_column`, `_sale_quotation_format_amount`.
- Script de prueba: `scripts/setup_quotation_test_emsoind.py`.

### Reversión del reporte de cotización (A3)

Al **desinstalar** `kc_fiscal_hn_v18`, los campos sobrescritos en
`sale.action_report_saleorder` **no se revierten** automáticamente; la acción puede
quedar apuntando a un template inexistente. Procedimiento de reversión:

1. Eliminar `report/sale_report_action.xml` del módulo (o comentar su carga en el manifest).
2. Ejecutar `-u sale` (o restaurar manualmente `report_name` /
   `report_file` / `paperformat_id` del reporte estándar).

Pro-forma (`sale.action_report_pro_forma`) permanece con formato Odoo estándar (fuera de v1).

## 18.0.1.1.6 — Fix: correlativo fiscal borrado a "/" al confirmar

- Corregido el caso en que, al confirmar una factura, el número de documento
  fiscal quedaba en `/` aunque el CAI y los rangos sí se asignaban.
- Causa: la numeración SAR la gobierna el CAI, pero Odoo intenta deducir el
  año/mes del propio número y, cuando "no coincide" con la fecha de la factura,
  el control nativo (`_compute_name` → `_set_next_sequence` /
  `_constrains_date_sequence`) reasigna `name` a `/`. Se hace evidente con un
  CAI que cruza de año o con grupos de dígitos del formato SAR
  (`000-001-01-correlativo`) que Odoo confunde con un año.
- Solución: `account.move._sequence_matches_date()` devuelve `True` para
  movimientos con numeración fiscal SAR (numeración externa, gobernada por el
  CAI), sin tocar la asignación del correlativo.

## 18.0.1.1.5 — Manual con compuerta por perfil + guía de importación

- Manual interno con **compuerta**: el contenido y las configuraciones solo se
  muestran tras **confirmar el tipo de empresa**; un botón "Cambiar tipo de
  empresa" permite volver al selector. Solo la confirmación adapta el manual.
- Navegación **estilo menú de Odoo, sin íconos** (más limpia y atractiva).
- Nueva sección **Importación de Datos** en el manual interno (especificación de
  columnas para categorías, productos y clientes, con accesos directos).
- Nuevas **plantillas CSV** de importación en `plantillas_importacion/`
  (categorías, productos, clientes).
- `MANUAL_USUARIO.md`: nueva sección **12. Importación de datos** con las
  plantillas y reglas de validación.

## 18.0.1.1.2 — Manual interactivo + documentación

- Manual de Uso interno **interactivo**: selector de tipo de empresa
  (pequeño/mediano/grande) y conmutador ZOLI que adaptan el contenido en vivo.
- Botones que **abren las pantallas reales** de configuración (compañía,
  contactos, diarios, códigos/impuestos SAR, secuencias, productos, libros,
  bloqueos Consumidor Final, DUCAs activos) y **rutas de menú** por sección.
- Nuevas secciones del manual: **Exoneración**, **Consumidor Final**,
  **Zona Libre (ZOLI)** y **Guía del Implementador**.
- Nuevo `MANUAL_USUARIO.md` (manual completo + clasificación para
  implementadores con el inventario de configuraciones).

## 18.0.1.1.1 — Control de exoneración y límite de Consumidor Final

- `res.company`: control de exoneración al facturar (advertencia/bloqueo) y
  alertas de vencimiento; límite de monto para Consumidor Final con bloqueo
  duro y auditoría (`kc_fiscal_hn.consumidor.final.audit`).

## 18.0.1.1.0 — Régimen de Zona Libre (ZOLI)

### Configuración por compañía (multicompañía)
- `res.company`: `es_zoli` y parámetros DUCA (días de permanencia 180,
  alerta previa 30, alerta crítica 7), responsables de compras/bodega,
  modo de control de vencidos y límite de ventas locales (50%).
- Todos los controles ZOLI se activan solo cuando `es_zoli = True`; las
  empresas de régimen normal no se ven afectadas.

### Bloque 1 — Control de permanencia (DUCA)
- `product`: `requiere_control_duca` (MP importada), `es_no_originario`,
  `porcentaje_dai_insumo`; valida `tracking='lot'`.
- `stock.lot`: número DUCA, fecha de ingreso, vencimiento (ingreso + días),
  documento adjunto, estado, días para vencer, stock disponible y
  autorización de gerencia para lotes vencidos.
- Recepción: exige N° DUCA y documento en MP importada.
- Bloqueo de uso de lotes vencidos en salidas y consumos (CMP), configurable.
- Cron diario de alertas (30 días, 7 días + correo, vencidos).
- Reporte de DUCAs activos (lista/pivot) y menú "Zona Libre (ZOLI)".

### Bloque 2 — Nacionalización
- `sale.order` / `account.move`: `tipo_operacion_zoli` (exportación /
  nacionalización), propagado de la OV a la factura.
- Motor de cálculo DAI: producto no originario → DAI sobre el bien final;
  producto originario (TLC) → DAI sobre insumos no originarios consumidos.
  ISV de nacionalización 15% sobre (base + DAI). Detalle en la factura.
- Cierre de DUCA: registra la cantidad nacionalizada al confirmar la factura.
- Dashboard Fiscal: control del límite del 50% de ventas locales anuales.

### Seguridad
- Grupo `group_zoli_gerencia` para autorizar el uso de lotes DUCA vencidos.

## 19.0.3.0.0 — Fase 3 (libros SAR persistentes + reportes PDF)

### Libros fiscales en base de datos
- `kc_fiscal_hn.book.sales`, `.purchases`, `.retentions`, `.exemptions`
- Estados: pendiente / declarado / rectificado (retenciones: pendiente / declarado)
- Generación desde facturas, listas editables, pivot/graph, exportación Excel
- `kc_fiscal_hn.book.audit` — historial de cambios (campo, valor anterior/nuevo, usuario)
- Chatter (`mail.thread`) con `tracking=True` en campos críticos

### Reportes PDF SAR
- Plantillas portadas desde `kc_fiscal_hn` (factura, NC, boleta, retención, guía)
- Factura: monto en letras vía `amount_words`
- Nota de crédito: motivo de emisión y factura original
- Guía: bloque CAI y fecha límite

### Menú
- **Libros SAR** con acceso a los cuatro libros, generador y auditoría

## 19.0.2.0.0 — Fase 2 (modelos y wizards)

### Modelos
- Portados desde `kc_fiscal_hn`: herencias contables, stock, secuencias SAR, alertas y auditoría.
- `account_move`: `amount_words`, `NumberUtilities`, `_compute_display_name` (sin `name_get`).
- `sequence_alert` / `sequence_audit`: `_compute_display_name`; auditoría con zona `America/Tegucigalpa`.
- `res_company`: `fiscal_resolution`, `fiscal_resolution_date`.
- `res_partner`: validación RTN activa.

### Wizards y controlador
- Todos los wizards portados; Excel migrado a **xlsxwriter** (sin xlwt).
- Controlador REST: `type='json'` (no jsonrpc).
- Utilidad compartida `wizard/excel_export.py`.

### Pendiente (Fase 3)
- Vistas XML, reportes QWeb PDF y menús (archivos stub en `views/` y `report/`).
