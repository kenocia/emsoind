# Manual de Usuario — Kenocia Fiscal Honduras v18

> Tropicalización fiscal completa de Odoo 18 para Honduras (SAR).
> Módulo: `kc_fiscal_hn_v18` · Autor: Kenocia (Kenosis Company) · Licencia: LGPL-3.

Este manual cubre **todas las opciones y configuraciones** del módulo, el flujo de
operación diaria y una **clasificación para implementadores** con el inventario
completo de parámetros (al final del documento).

---

## Índice

1. [Visión general](#1-visión-general)
2. [Requisitos e instalación](#2-requisitos-e-instalación)
3. [Roles y permisos](#3-roles-y-permisos)
4. [Mapa de menús](#4-mapa-de-menús)
5. [Orden de configuración recomendado](#5-orden-de-configuración-recomendado)
6. [Configuración detallada](#6-configuración-detallada)
   - [6.1 Compañía (Información SAR)](#61-compañía-información-sar)
   - [6.2 Contactos (RTN, constancias, exoneración)](#62-contactos-rtn-constancias-exoneración)
   - [6.3 Diarios contables](#63-diarios-contables)
   - [6.4 Códigos SAR e Impuestos](#64-códigos-sar-e-impuestos)
   - [6.5 Secuencias fiscales y rangos CAI](#65-secuencias-fiscales-y-rangos-cai)
   - [6.6 Productos](#66-productos)
7. [Operación diaria](#7-operación-diaria)
   - [7.1 Facturas de venta](#71-facturas-de-venta)
   - [7.2 Facturas de compra](#72-facturas-de-compra)
   - [7.3 Retenciones ISR](#73-retenciones-isr)
   - [7.4 Control de exoneración al facturar](#74-control-de-exoneración-al-facturar)
   - [7.5 Límite de Consumidor Final](#75-límite-de-consumidor-final)
   - [7.6 Libros SAR](#76-libros-sar)
   - [7.7 Dashboard fiscal](#77-dashboard-fiscal)
   - [7.8 Informes Excel](#78-informes-excel)
   - [7.9 Cierre mensual](#79-cierre-mensual)
8. [Automatizaciones (cron)](#8-automatizaciones-cron)
9. [Auditoría y trazabilidad](#9-auditoría-y-trazabilidad)
10. [Preguntas frecuentes y solución de problemas](#10-preguntas-frecuentes-y-solución-de-problemas)
11. [Clasificación para Implementadores](#11-clasificación-para-implementadores)
12. [Importación de datos (plantillas Excel/CSV)](#12-importación-de-datos-plantillas-excelcsv)

---

## 1. Visión general

El módulo implementa los requerimientos del **SAR (Servicio de Administración
de Rentas)** de Honduras:

- **Secuencias SAR con CAI**, rangos y fechas límite de emisión.
- **ISV 15% / 18%**, exento y exonerado.
- **Validación de RTN** Honduras (14 dígitos empresa, 13 persona natural).
- **Retenciones ISR** (12.5% servicios, 1% bienes, 10% alquiler).
- **Reportes fiscales PDF** (Factura, NC, ND, Boleta, Retención, Guía de remisión).
- **Reportes Excel** (Ventas, DMC, SAR, Retenciones, Exoneraciones, Detalle).
- **Libros SAR persistentes** (Ventas, Compras/DMC, Retenciones, Exoneraciones).
- **Control de exoneración** al facturar y alertas de vencimiento.
- **Límite de monto para Consumidor Final** con bloqueo y auditoría.
- **Alertas y auditoría** de secuencias, libros y controles fiscales.

---

## 2. Requisitos e instalación

| Requisito | Detalle |
|---|---|
| Versión Odoo | 18.0 |
| Módulos requeridos | `base`, `web`, `mail`, `hr`, `account`, `sale`, `purchase`, `stock`, `stock_account`, `purchase_stock`, `sale_stock` |
| Dependencias Python | `openpyxl`, `xlsxwriter` |
| País | Honduras (`HN`) — moneda `HNL` |

**Instalación:** activar modo desarrollador → *Aplicaciones* → buscar
"Kenocia Fiscal Honduras v18" → *Instalar*. El módulo ejecuta un
`post_init_hook` que carga datos iniciales (códigos SAR, etc.).

Para aplicar cambios posteriores del módulo: actualizar con
`-u kc_fiscal_hn_v18` o desde *Aplicaciones → Actualizar*.

---

## 3. Roles y permisos

| Grupo | Nombre | Para qué sirve |
|---|---|---|
| `group_fiscal_sequence_manager` | Administrador de Numeración Fiscal | Cancelar/eliminar facturas fiscales SAR, gestionar libros y códigos SAR, y **omitir el bloqueo duro de exoneración vencida**. Implica `account.group_account_manager`. |
| `account.group_account_user` | Usuario de Contabilidad | Operación diaria: facturar, registrar compras, ver libros e informes. |
| `account.group_account_manager` | Responsable de Contabilidad | Gestión completa de libros, códigos SAR y auditorías. |

> El **límite de Consumidor Final** es un bloqueo duro **sin excepción**: ningún
> perfil puede saltárselo (ver sección 7.5).

---

## 4. Mapa de menús

Menú raíz: **Fiscal HN**

- **Dashboard Fiscal**
- **Configuraciones**
  - Secuencias Fiscales
  - Diarios Fiscales
  - Preregistro CAI
  - Alertas de Secuencias
  - Alertas Avanzadas
  - Auditoría de Secuencias
  - Códigos SAR
  - Impuestos SAR
  - Salud Fiscal
- **Validaciones**
  - Validación Fiscal Masiva
  - Reiniciar Secuencia
  - Bloqueos Consumidor Final
- **Libros SAR**
  - Libro de Ventas
  - Libro de Compras (DMC)
  - Libro de Retenciones
- **Informes Excel**
  - Ventas Netas · Ventas SAR · DMC Compras · Retenciones SAR · Exoneraciones SAR · Detalle Facturas
- **📖 Manual de Uso** (manual interactivo dentro de Odoo)

---

## 5. Orden de configuración recomendado

1. **Compañía** — RTN, resolución SAR, tipo de contribuyente.
2. **Códigos SAR e Impuestos** — verificar que existen y están vinculados.
3. **Diarios contables** — definir el documento fiscal de cada diario.
4. **Secuencias fiscales con CAI** — crear y cargar rangos CAI.
5. **Vincular secuencias a los diarios**.
6. **Contactos** — RTN, constancias, exoneración.
7. **Productos** — retención ISR, categoría fiscal.
8. **Control de exoneración y límite de Consumidor Final** (compañía).
9. **Emitir facturas** de venta y compra.
10. **Generar Libros SAR** y declarar.

---

## 6. Configuración detallada

### 6.1 Compañía (Información SAR)

**Ruta:** *Ajustes → Compañías → [Tu empresa] → pestaña "Información SAR"*.

**Clasificación SAR Honduras**

| Campo | Descripción |
|---|---|
| RTN Empresa | 14 dígitos numéricos, sin guiones. |
| Clasificación SAR (`tipo_contribuyente`) | Pequeño / Mediano / Grande. Determina obligaciones. |
| N° Contribuyente SAR | Número asignado por el SAR. |
| Fecha Clasificación SAR | Fecha de clasificación. |
| Régimen Especial | Si aplica, también obliga a DMC. |

Obligaciones calculadas automáticamente (solo lectura): **Obligado a DMC**,
**Agente de Retención ISV**, **Requiere Libro DMC**, **Nivel de Control Fiscal**
(básico / intermedio / completo).

- **Pequeño:** no obligado a DMC.
- **Mediano:** obligado a DMC mensual.
- **Grande:** DMC mensual + agente de retención ISV 15%.

**Control de exoneración (clientes)**

| Campo | Default | Descripción |
|---|---|---|
| Control de exoneración al facturar (`exoneracion_modo_control`) | Advertencia | `Sin control` / `Advertencia` / `Bloqueo duro`. |
| Días de alerta de vencimiento (`exoneracion_dias_alerta`) | 30 | Días antes del vencimiento para notificar. |
| Responsable de zona (respaldo) (`exoneracion_responsable_id`) | — | Usuario que recibe alertas si el cliente no tiene vendedor. |

**Límite de Consumidor Final**

| Campo | Default | Descripción |
|---|---|---|
| Controlar monto de Consumidor Final (`consumidor_final_control_activo`) | Activado | Activa el bloqueo. |
| Contacto Consumidor Final (`consumidor_final_partner_id`) | — | Contacto genérico que representa al Consumidor Final. |
| Monto máximo Consumidor Final (`consumidor_final_monto_maximo`) | 0 | Tope por documento (impuestos incluidos). 0 = sin límite. |

**Resolución y registro SAR:** N° de resolución, fecha, imagen de información
bancaria y de términos y condiciones (para los reportes).

### 6.2 Contactos (RTN, constancias, exoneración)

**Ruta:** *Contactos → [contacto] → pestaña "🇭🇳 Fiscal Honduras"*.

**Datos base**

- **País** (obligatorio).
- **RTN** (`vat`): 14 dígitos (empresa) o 13 (persona natural) si es Honduras.
  El módulo valida formato y unicidad.
- **Empresa/Persona** (`is_company`): define la longitud esperada del RTN.

**Clasificación fiscal automática** (`tipo_fiscal_proveedor`): nacional con RTN
(empresa/persona), nacional sin RTN (boleta), extranjero CA, extranjero. Define
el **diario de compra sugerido** (`diario_compra_sugerido_id`).

**Constancia de Pago a Cuenta SAR** (proveedores)

| Campo | Descripción |
|---|---|
| Tiene Constancia de Pago a Cuenta | Si está vigente, **no se retiene ISR**. |
| N° Constancia SAR | Número de la constancia. |
| Vence Constancia | Cuotas: 30 Jun, 30 Sep, 31 Dic. |
| Constancia PDF/Imagen | Adjunto de respaldo. |
| Estado Constancia (auto) | Vigente / Próxima / Vencida / Sin constancia. |

**Exoneración SAR** (clientes)

| Campo | Descripción |
|---|---|
| Tiene Exoneración SAR | El cliente tiene Orden de Compra Exonerada (OCE) vigente. |
| N° Constancia Exoneración | Número de la OCE. |
| Vence Exoneración | Fecha de vencimiento del acuerdo. |
| Constancia Exoneración PDF | Adjunto. |
| Estado Exoneración (auto) | Vigente / Próxima / Vencida / Sin exoneración. |

### 6.3 Diarios contables

**Ruta:** *Contabilidad → Configuración → Diarios* (o *Fiscal HN →
Configuraciones → Diarios Fiscales*).

| Campo | Descripción |
|---|---|
| Documento Fiscal (`document_fiscal`) | Factura Cliente / Factura Proveedor (FA) / Boleta / Importación (DUA/FYDUCA) / Comprobante de Retención / Nota de Crédito / Nota de Débito. |
| Secuencia Fiscal SAR (`fiscal_sequence_id`) | Secuencia para correlativos de facturas. |
| Secuencia Fiscal Notas de Crédito (`refund_fiscal_sequence_id`) | Secuencia para NC (no puede ser la misma que facturas). |

Campos informativos (solo lectura): CAI vigente, consumo CAI, vencimiento CAI,
estado CAI, y **estado de configuración fiscal** (Configurado / Sin documento /
Sin secuencia / CAI en alerta / CAI crítico).

> **Automático:** al elegir el proveedor en una factura de compra, el diario se
> asigna según la clasificación fiscal del contacto.

#### Configuración recomendada de Notas de Crédito y Débito

- **Notas de crédito (NC):** se emiten desde el **mismo diario de facturas**.
  En el diario *Factura Cliente* (o *Factura Proveedor*) se llenan dos campos:
  - `fiscal_sequence_id` (**Secuencia Fiscal SAR**) → numera las facturas
    (`FAC/…`).
  - `refund_fiscal_sequence_id` (**Secuencia Fiscal Notas de Crédito**) →
    numera las NC (`NC/…`). La devolución/reembolso (`out_refund` / `in_refund`)
    toma esta secuencia **automáticamente**. No se requiere un diario dedicado
    de NC. La secuencia de NC **no puede ser la misma** que la de facturas.
- **Notas de débito (ND):** requieren un **diario dedicado** con
  `document_fiscal = Nota de Débito` y su propia secuencia ND. La ND no se
  enruta por el campo de refund; si se emitiera desde el diario de facturas
  tomaría el CAI de facturas (incorrecto).
- **Requisito común:** cada secuencia (FAC, NC, ND) debe tener un **rango CAI
  vigente** (ver 6.5); sin él, el documento no se puede emitir.

| Documento | Tipo Odoo | Diario | Secuencia que aplica |
|---|---|---|---|
| Factura cliente | `out_invoice` | Facturas de cliente | Secuencia Fiscal SAR (FAC) |
| Nota de crédito cliente | `out_refund` | Facturas de cliente (el mismo) | Secuencia Fiscal NC |
| Nota de débito cliente | `out_invoice` (debit) | Notas de Débito Clientes (dedicado) | Secuencia Fiscal ND |

### 6.4 Códigos SAR e Impuestos

**Códigos SAR** — *Fiscal HN → Configuraciones → Códigos SAR*. El módulo carga
los códigos oficiales. Campos: `codigo`, `nombre`, `tipo_impuesto`
(ISV/Retención/Exento/Exonerado/Otros), `tipo_uso` (Ventas/Compras/Ambos),
`porcentaje`, `base_legal`, `activo`.

**Impuestos SAR** — *Fiscal HN → Configuraciones → Impuestos SAR*. En cada
impuesto (`account.tax`) configurar:

| Campo | Descripción |
|---|---|
| Código SAR Honduras (`codigo_sar_id`) | Vincula el impuesto a un código oficial. Al elegirlo, autocompleta tipo, %, y banderas. |
| Tipo de Impuesto SAR (`tipo_impuesto`) | ISV / Retención / Exento / Exonerado / Otros. |
| Es Deducible / Aplica Retención / Es Retención | Banderas de comportamiento. |

Códigos típicos: `01` ISV 15% ventas · `02` ISV 18% ventas · `03` Exento ·
`04` Exonerado · `05` Retención ISV 15% · `06`/`07` ISV compras · `08` ISR 12.5% ·
`09` ISR 1% · `10` ISR 10%.

### 6.5 Secuencias fiscales y rangos CAI

**Ruta:** *Fiscal HN → Configuraciones → Secuencias Fiscales*.

El **CAI (Clave de Autorización de Impresión)** lo emite el SAR para autorizar
documentos fiscales. **Sin CAI vigente no se pueden emitir facturas.**

**Secuencia (`ir.sequence`)**

| Campo | Default | Descripción |
|---|---|---|
| Es Secuencia Fiscal (`is_fiscal`) | No | Activa el control fiscal SAR. |
| Tipo Fiscal (`fiscal_type`) | Factura | Factura / NC / ND / Recibo / Retención / Otro. |
| Default días de alerta (`default_dias_alerta`) | 5 | Valor inicial de alerta por días en rangos nuevos. |
| Default correlativos de alerta (`default_numeros_alerta`) | 10 | Valor inicial de alerta por correlativos en rangos nuevos. |
| Umbral de Alerta (%) (`alert_threshold`) | 80 | % de rango usado para alertar. |
| Umbral de Advertencia (%) (`warning_threshold`) | 90 | % de rango usado para advertir. |
| Alertas Automáticas (`auto_alert`) | Sí | Activa alertas. |
| Requiere/Validar CAI, Validar RTN | Sí | Validaciones SAR. |

**Rango CAI (`ir.sequence.date_range`)** — pestaña de rangos:

| Campo | Default | Descripción |
|---|---|---|
| Desde / Hasta (`date_from`/`date_to`) | — | Vigencia del CAI. |
| CAI (`cai`) | — | Código emitido por el SAR. |
| Rango inicial / final (`rangoInicial`/`rangoFinal`) | — | Números autorizados. |
| Alertar días antes (`dias_alerta`) | 5 | Días antes de "Hasta" para advertir (0 = off). |
| Alertar correlativos restantes (`numeros_alerta`) | 10 | Aviso al quedar N correlativos (0 = off). |

Atajo: botón **Preregistrar CAI** para un flujo guiado. Finalmente, vincular la
secuencia al diario (sección 6.3).

### 6.6 Productos

**Ruta:** *Inventario → Productos → [producto] → pestaña "🇭🇳 Fiscal Honduras"*.

| Campo | Descripción |
|---|---|
| Aplica Retención ISR (`aplica_retencion_isr`) | Aplica ISR automáticamente cuando el proveedor **no** tiene constancia vigente. |
| Impuesto de Retención ISR (`impuesto_retencion_isr_id`) | ISR 12.5% (honorarios) / 1% (bienes) / 10% (alquiler). Obligatorio si lo anterior está marcado. |
| Categoría Fiscal (`categoria_fiscal`) | Bienes / Servicios / Ambos. |
| Tipo Servicio Retención (`tipo_servicio_retencion`) | Para el libro de retenciones (transporte, alquiler, seguridad, etc.). |
| Es Exento / Es Exonerado | Banderas para impuestos. |

**Régimen Zona Libre (ZOLI) / DUCA / DAI** (si aplica): `requiere_control_duca`,
`es_no_originario`, `porcentaje_dai_insumo`, `es_originario_tlc`, `codigo_sac`,
`porcentaje_dai`.

---

## 7. Operación diaria

### 7.1 Facturas de venta

**Ruta:** *Contabilidad → Clientes → Facturas → Nueva*.

1. Seleccionar **cliente** con RTN configurado.
2. Verificar diario de ventas con secuencia fiscal asignada.
3. Agregar líneas con el ISV correcto (15% / Exento / Exonerado).
4. Revisar la **pestaña SAR** (ISV, exentos, exonerados, base imponible).
5. **Confirmar.** El sistema asigna correlativo fiscal, CAI vigente, fecha
   límite de emisión y rango.

> Las facturas fiscales confirmadas **no** se cancelan directamente; se anulan
> con una **Nota de Crédito**. Solo el Administrador de Numeración Fiscal puede
> cancelar excepcionalmente.

### 7.2 Facturas de compra

**Ruta:** *Contabilidad → Proveedores → Facturas → Nueva*.

1. Seleccionar **proveedor** → el diario se asigna automáticamente (CFA/BOL/IMP).
2. Aparece la **alerta fiscal** con el estado de constancia y la retención.
3. Completar la pestaña SAR (CAI del proveedor, correlativo, fecha, clase FA/OC).
4. Agregar líneas → ISV y retención ISR se aplican automáticamente.
5. Confirmar.

### 7.3 Retenciones ISR

Se retiene ISR cuando: proveedor HN con RTN **y** sin constancia vigente **y**
el producto aplica retención. No se retiene si hay constancia vigente, es
extranjero, es boleta (sin RTN) o el producto no aplica retención.

| Tipo | Tasa | Aplica a |
|---|---|---|
| Servicios/Honorarios | 12.5% | Consultoría, asesoría, servicios técnicos |
| Anticipo Bienes | 1% | Compra de mercadería y bienes |
| Alquiler | 10% | Alquiler habitacional > L.15,000/mes |

**Retención ISV 15% (solo Grandes Contribuyentes).** Los grandes son **agentes
de retención del ISV 15%** (código SAR `05`): al pagar servicios afectos
(transporte, alquiler, maquinaria/equipo) retienen el 15% del ISV al proveedor y
lo enteran al SAR. Se activa automáticamente cuando la compañía es Grande
Contribuyente. En el manual interno, este bloque solo se muestra para el perfil
"Grande".

El **Libro de Retenciones** consolida lo del mes para enterar al SAR.

### 7.4 Control de exoneración al facturar

Cuando una **factura de venta** lleva impuesto **exonerado** (monto exonerado > 0),
el sistema verifica que el cliente tenga una exoneración **vigente** a la fecha
del documento. Se considera **no vigente** si: no tiene exoneración registrada,
no tiene fecha de vencimiento, o la fecha ya pasó.

Comportamiento según `exoneracion_modo_control` (compañía):

- **Sin control:** no valida.
- **Advertencia:** muestra un aviso y permite continuar.
- **Bloqueo duro:** impide confirmar; **solo** el Administrador de Numeración
  Fiscal puede continuar (con aviso).

Además, un cron diario **notifica** (actividad To-Do) al vendedor del cliente
(o al responsable de respaldo) cuando la exoneración está **próxima a vencer**
(según `exoneracion_dias_alerta`) o ya **vencida**.

### 7.5 Límite de Consumidor Final

Si la compañía tiene activado el control y configurado el **contacto Consumidor
Final** y un **monto máximo**, al **confirmar una orden de venta** o **validar
una factura de venta** a nombre de ese contacto cuyo **total (con impuestos)**
supere el máximo, la transacción se **bloquea**.

- Es un **bloqueo duro sin excepción**: ningún perfil puede continuar.
- Mensaje al usuario: debe **registrar un contacto formal con RTN** y asignarlo.
- Cada intento bloqueado se **registra en auditoría** (ver 9), incluso aunque la
  transacción se revierta.

### 7.6 Libros SAR

**Ruta:** *Fiscal HN → Libros SAR*.

- **Libro de Ventas:** facturas, NC y ND emitidas.
- **Libro de Compras (DMC):** FA (Sección A), Boletas (B), Importaciones (C),
  NC/ND de proveedores. Plazo: primeros **8 días hábiles** del mes siguiente
  (solo medianos y grandes).
- **Libro de Retenciones:** retenciones ISR aplicadas. Plazo: primeros **10 días
  hábiles**.

Flujo: *Nuevo → configurar período → Generar Libro → revisar → Marcar Declarado
→ Exportar Excel*.

### 7.7 Dashboard fiscal

**Ruta:** *Fiscal HN → Dashboard Fiscal*. KPIs: ISV neto, ISV ventas/compras,
retenciones, n.º de facturas, clientes únicos, ticket promedio, facturas sin RTN,
NC/ND, anuladas, guías, correlativos usados/disponibles, días CAI vigente y
estado de declaraciones.

### 7.8 Informes Excel

**Ruta:** *Fiscal HN → Informes Excel*.

| Reporte | Contenido / uso |
|---|---|
| Ventas Netas | Detalle por producto y vendedor. |
| Ventas SAR | Formato SAR (correlativo, RTN, ISV, exentos). |
| DMC Compras | Secciones A/B/C con clase FA/OC. |
| Retenciones SAR | Retenciones por proveedor y tipo. |
| Exoneraciones SAR | Ventas con OCE por cliente. |
| Detalle Facturas | Línea por línea con impuestos. |

### 7.9 Cierre mensual

Checklist: verificar facturas/compras confirmadas → generar libros (Ventas,
DMC, Retenciones) → verificar consistencia → declarar dentro de plazos → exportar
Excel de respaldo → revisar dashboard, constancias por vencer y estado CAI.

---

## 8. Automatizaciones (cron)

| Cron | Frecuencia | Qué hace |
|---|---|---|
| Activar Rango CAI Fiscal HN (`cron_activar_rango_cai`) | Diario | Activa automáticamente el siguiente rango CAI según fechas. |
| Alertas Constancias Pago a Cuenta SAR (`cron_alertas_constancias`) | Diario | Crea actividades para constancias próximas a vencer o vencidas. |
| Alertas Vencimiento Exoneración SAR (`cron_alertas_exoneracion`) | Diario | Notifica al responsable de zona exoneraciones próximas o vencidas (idempotente). |

---

## 9. Auditoría y trazabilidad

- **Auditoría de Secuencias** (*Configuraciones → Auditoría de Secuencias*):
  reinicios, modificaciones, creaciones y eliminaciones de secuencias (con
  usuario, fecha, IP y motivo).
- **Bloqueos Consumidor Final** (*Validaciones → Bloqueos Consumidor Final*):
  cada intento de superar el límite (usuario, cliente, documento, monto, IP).
- **Chatter en Secuencias Fiscales:** los cambios de configuración y de rangos
  CAI quedan registrados en el historial de mensajes de cada secuencia fiscal.
- **Libros SAR:** auditoría de generación/declaración de libros.

---

## 10. Preguntas frecuentes y solución de problemas

**No puedo emitir facturas: "Sin CAI vigente".** Cargar un rango CAI vigente en
la secuencia fiscal del diario (sección 6.5).

**No aparecen los campos fiscales del impuesto.** Abrir el impuesto desde
*Fiscal HN → Configuraciones → Impuestos SAR*; la sección SAR es siempre visible.

**No se retiene ISR a un proveedor.** Verificar que el proveedor sea HN con RTN,
sin constancia vigente, y que el producto tenga "Aplica Retención ISR".

**La factura exonerada bloquea/advierte.** Revisar la exoneración del cliente
(sección 6.2) y el modo de control en la compañía (sección 6.1).

**No puedo confirmar una venta a Consumidor Final.** El total supera el máximo;
registrar un contacto con RTN (sección 7.5).

---

## 11. Clasificación para Implementadores

Inventario completo de **todas las configuraciones** del módulo, por área. Útil
para puesta en marcha (onboarding) y checklists de implementación.

### 11.1 Compañía — `res.company`
Ruta: *Ajustes → Compañías → Información SAR*.

| Campo técnico | Etiqueta | Tipo | Default | Oblig. | Notas |
|---|---|---|---|---|---|
| `rtn_empresa` | RTN Empresa | Char | — | Sí | 14 dígitos. |
| `tipo_contribuyente` | Clasificación SAR | Selection | pequeño | Sí | pequeño/mediano/grande. |
| `numero_contribuyente_sar` | N° Contribuyente SAR | Char | — | No | |
| `fecha_clasificacion_sar` | Fecha Clasificación SAR | Date | — | No | |
| `regimen_especial` | Régimen Especial | Boolean | False | No | Obliga a DMC. |
| `fiscal_resolution` | Resolución SAR | Char | — | No | Para reportes. |
| `fiscal_resolution_date` | Fecha Resolución SAR | Date | — | No | |
| `banking_information_image` | Información Bancaria | Binary | — | No | Imagen para reportes. |
| `terms_conditions_image` | Términos y Condiciones | Binary | — | No | Imagen para reportes. |
| `exoneracion_modo_control` | Control de exoneración al facturar | Selection | advertencia | Sí | ninguno/advertencia/bloqueo. |
| `exoneracion_dias_alerta` | Días de alerta exoneración | Integer | 30 | No | |
| `exoneracion_responsable_id` | Responsable de zona (respaldo) | Many2one(res.users) | — | No | |
| `consumidor_final_control_activo` | Controlar monto Consumidor Final | Boolean | True | No | |
| `consumidor_final_partner_id` | Contacto Consumidor Final | Many2one(res.partner) | — | Si activo | |
| `consumidor_final_monto_maximo` | Monto máximo Consumidor Final | Monetary | 0 | No | 0 = sin límite. |
| *(auto)* `obligado_dmc`, `es_agente_retencion`, `requiere_libro_dmc`, `nivel_control_fiscal` | Obligaciones | computados | — | — | Solo lectura. |

### 11.2 Contacto — `res.partner`
Ruta: *Contactos → pestaña Fiscal Honduras*.

| Campo técnico | Etiqueta | Tipo | Default | Notas |
|---|---|---|---|---|
| `vat` | RTN | Char | — | 14/13 dígitos HN; validado. |
| `is_company` | Empresa/Persona | Boolean | — | Define longitud RTN. |
| `tipo_fiscal_proveedor` | Clasificación Fiscal | Selection (auto) | — | Solo lectura. |
| `diario_compra_sugerido_id` | Diario Compra Sugerido | Many2one (auto) | — | Solo lectura. |
| `tiene_constancia_pago_cuenta` | Tiene Constancia | Boolean | False | |
| `numero_constancia_pago_cuenta` | N° Constancia SAR | Char | — | |
| `fecha_vencimiento_constancia` | Vence Constancia | Date | — | |
| `imagen_constancia` | Constancia PDF/Imagen | Binary | — | |
| `constancia_vigente`, `dias_vencimiento_constancia`, `alerta_constancia` | Estado constancia | computados | — | Solo lectura. |
| `tiene_exoneracion_sar` | Tiene Exoneración SAR | Boolean | False | |
| `numero_exoneracion_sar` | N° Constancia Exoneración | Char | — | |
| `fecha_vencimiento_exoneracion` | Vence Exoneración | Date | — | |
| `imagen_exoneracion` | Constancia Exoneración PDF | Binary | — | |
| `exoneracion_vigente`, `dias_vencimiento_exoneracion`, `alerta_exoneracion` | Estado exoneración | computados | — | Solo lectura. |

### 11.3 Diario — `account.journal`
Ruta: *Contabilidad → Diarios* / *Fiscal HN → Diarios Fiscales*.

| Campo técnico | Etiqueta | Tipo | Notas |
|---|---|---|---|
| `document_fiscal` | Documento Fiscal | Selection | client/vendors/boleta/importacion/retention/credit/debit. |
| `fiscal_sequence_id` | Secuencia Fiscal SAR | Many2one(ir.sequence) | Domain `is_fiscal=True`. |
| `refund_fiscal_sequence_id` | Secuencia Fiscal NC | Many2one(ir.sequence) | Distinta a la de facturas. |
| `fiscal_config_state`, `fiscal_is_operational` | Estado configuración fiscal | computados | Solo lectura. |

### 11.4 Impuesto — `account.tax`
Ruta: *Fiscal HN → Impuestos SAR*.

| Campo técnico | Etiqueta | Tipo | Default | Notas |
|---|---|---|---|---|
| `codigo_sar_id` | Código SAR Honduras | Many2one(codigo.sar) | — | Autocompleta tipo/%. |
| `tipo_impuesto` | Tipo de Impuesto SAR | Selection | isv | isv/retencion/exento/exonerado/otros. |
| `es_deducible` | Es Deducible | Boolean | True | |
| `aplica_retencion` | Aplica Retención | Boolean | False | |
| `is_retention` | Es Retención | Boolean | False | |

### 11.5 Código SAR — `kc_fiscal_hn.codigo.sar`
Ruta: *Fiscal HN → Códigos SAR*.

| Campo técnico | Etiqueta | Tipo | Notas |
|---|---|---|---|
| `codigo` | Código SAR | Char | Único. |
| `nombre` | Nombre | Char | |
| `tipo_impuesto` | Tipo de Impuesto | Selection | |
| `tipo_uso` | Uso | Selection | sale/purchase/all. |
| `porcentaje` | Porcentaje (%) | Float | |
| `base_legal` | Base Legal | Char | |
| `activo` | Activo | Boolean | |

### 11.6 Secuencia fiscal — `ir.sequence`
Ruta: *Fiscal HN → Secuencias Fiscales*.

| Campo técnico | Etiqueta | Tipo | Default | Notas |
|---|---|---|---|---|
| `is_fiscal` | Es Secuencia Fiscal | Boolean | False | |
| `fiscal_type` | Tipo Fiscal | Selection | invoice | invoice/credit_note/debit_note/receipt/retention/other. |
| `default_dias_alerta` | Default días de alerta | Integer | 5 | |
| `default_numeros_alerta` | Default correlativos de alerta | Integer | 10 | |
| `alert_threshold` | Umbral de Alerta (%) | Integer | 80 | |
| `warning_threshold` | Umbral de Advertencia (%) | Integer | 90 | |
| `auto_alert` | Alertas Automáticas | Boolean | True | |
| `requires_cai` / `cai_validation` / `rtn_validation` | Validaciones SAR | Boolean | True | |

### 11.7 Rango CAI — `ir.sequence.date_range`

| Campo técnico | Etiqueta | Tipo | Default | Notas |
|---|---|---|---|---|
| `date_from` / `date_to` | Desde / Hasta | Date | — | Vigencia. |
| `cai` | CAI | Char | — | Código SAR. |
| `rangoInicial` / `rangoFinal` | Rango inicial / final | Integer | — | |
| `dias_alerta` | Alertar días antes | Integer | 5 | 0 = off. |
| `numeros_alerta` | Alertar correlativos restantes | Integer | 10 | 0 = off. |

### 11.8 Producto — `product.template`
Ruta: *Inventario → Productos → pestaña Fiscal Honduras*.

| Campo técnico | Etiqueta | Tipo | Default | Notas |
|---|---|---|---|---|
| `aplica_retencion_isr` | Aplica Retención ISR | Boolean | False | |
| `impuesto_retencion_isr_id` | Impuesto de Retención ISR | Many2one(account.tax) | — | Oblig. si aplica retención. |
| `categoria_fiscal` | Categoría Fiscal | Selection | bienes | bienes/servicios/ambos. |
| `tipo_servicio_retencion` | Tipo Servicio Retención | Selection | — | Para libro retenciones. |
| `es_exento` / `es_exonerado` | Exento / Exonerado | Boolean | False | |
| `requiere_control_duca` | Requiere control DUCA | Boolean | False | ZOLI; exige lote. |
| `es_no_originario` | Insumo no originario | Boolean | True | DAI. |
| `porcentaje_dai_insumo` | % DAI del insumo | Float | 0 | |
| `es_originario_tlc` | Producto originario (TLC) | Boolean | False | |
| `codigo_sac` | Código SAC | Char | — | |
| `porcentaje_dai` | % DAI del producto | Float | 0 | |

### 11.9 Régimen de Zona Libre (ZOLI) — `res.company`
Ruta: *Ajustes → Compañías → Información SAR → Régimen de Zona Libre (ZOLI)*.
Todos los controles se activan solo si `es_zoli = True`.

| Campo técnico | Etiqueta | Tipo | Default | Notas |
|---|---|---|---|---|
| `es_zoli` | Empresa bajo régimen ZOLI | Boolean | False | Interruptor maestro. |
| `duca_dias_permanencia` | Días de permanencia DUCA | Integer | 180 | Vencimiento = recepción + días. |
| `duca_dias_alerta_previa` | Días de alerta previa DUCA | Integer | 30 | Primera alerta. |
| `duca_dias_alerta_critica` | Días de alerta crítica DUCA | Integer | 7 | Alerta + correo. |
| `duca_responsable_compras_id` | Responsable de Compras (ZOLI) | Many2one(res.users) | — | |
| `duca_responsable_bodega_id` | Responsable de Bodega (ZOLI) | Many2one(res.users) | — | |
| `duca_modo_vencidos` | Control de lotes DUCA vencidos | Selection | bloqueo | advertencia/bloqueo. |
| `zoli_limite_local_pct` | Límite de ventas locales (%) | Float | 50 | Máximo legal. |
| `zoli_limite_alerta_pct` | Umbral de alerta (%) | Float | 45 | Aviso en dashboard. |

Relacionado: producto (`requiere_control_duca`, `es_no_originario`,
`porcentaje_dai_insumo`, `es_originario_tlc`, `codigo_sac`, `porcentaje_dai`),
`stock.lot` (N° DUCA, vencimiento), OV/factura (`tipo_operacion_zoli`:
exportación / nacionalización). Grupo `group_zoli_gerencia` autoriza el uso de
lotes DUCA vencidos. Menú: *Fiscal HN → Zona Libre (ZOLI) → DUCAs Activos*.

### 11.10 Seguridad y automatización

| Elemento | XML ID | Tipo |
|---|---|---|
| Administrador de Numeración Fiscal | `group_fiscal_sequence_manager` | res.groups |
| Gerencia ZOLI (lotes DUCA vencidos) | `group_zoli_gerencia` | res.groups |
| Activar Rango CAI | `cron_activar_rango_cai` | ir.cron (diario) |
| Alertas Constancias | `cron_alertas_constancias` | ir.cron (diario) |
| Alertas Exoneración | `cron_alertas_exoneracion` | ir.cron (diario) |
| Alertas DUCA ZOLI | (cron en `stock.lot`) | ir.cron (diario) |

### 11.11 Checklist de implementación

- [ ] Compañía: RTN, tipo contribuyente, resolución SAR.
- [ ] Compañía: modo de exoneración y límite de Consumidor Final.
- [ ] Códigos SAR cargados y verificados.
- [ ] Impuestos con `codigo_sar_id` vinculado.
- [ ] Diarios con documento fiscal y secuencias asignadas.
- [ ] Secuencias fiscales con rangos CAI vigentes.
- [ ] Contactos con RTN; proveedores con constancia; clientes con exoneración.
- [ ] Productos con retención ISR e impuesto configurado.
- [ ] Crons activos (rango CAI, constancias, exoneración).
- [ ] Permisos asignados (Administrador de Numeración Fiscal).
- [ ] Prueba de extremo a extremo: venta, compra, retención, libros, Excel.

---

## 12. Importación de datos (plantillas Excel/CSV)

Odoo importa desde la **vista de lista** del modelo correspondiente:
*Favoritos → Importar registros*. Acepta archivos **.xlsx** y **CSV (UTF-8)**.

> **Orden recomendado:** **1) Categorías → 2) Productos → 3) Clientes**.
> Productos referencia categorías, por eso las categorías van primero.

Las plantillas listas para rellenar están en el módulo, carpeta
`plantillas_importacion/`:

- `1_plantilla_categorias.csv`
- `2_plantilla_productos.csv`
- `3_plantilla_clientes.csv`

**Reglas generales:**

- No cambies los nombres de las columnas (encabezados) de la primera fila.
- Una fila por registro; usa **punto** como separador decimal.
- El campo `id` (External ID) es opcional pero recomendado: permite
  **reimportar para actualizar** sin duplicar.
- Para campos booleanos usa `VERDADERO`/`FALSO` (o `1`/`0`).
- Fechas en formato `AAAA-MM-DD`.
- Haz una prueba con 2–3 filas antes de la carga masiva.

### 12.1 Categorías de producto (`product.category`)

Ruta: *Inventario → Configuración → Categorías de productos → Importar*.

| Columna | Obligatorio | Descripción / validación |
|---|---|---|
| `id` | No | External ID único (ej. `cat_servicios`). |
| `name` | Sí | Nombre de la categoría. |
| `parent_id` | No | Categoría padre (nombre exacto o External ID). Debe existir. |

### 12.2 Productos (`product.template`)

Ruta: *Inventario → Productos → Importar* (o *Ventas → Productos*).

| Columna | Obligatorio | Descripción / validación |
|---|---|---|
| `name` | Sí | Nombre del producto. |
| `default_code` | No | Referencia interna / SKU. |
| `type` | Sí | `consu` (bienes) o `service` (servicios). |
| `categ_id` | Sí | Categoría (nombre exacto o External ID). Debe existir. |
| `list_price` | No | Precio de venta. |
| `standard_price` | No | Costo. |
| `taxes_id` | Recom. | Impuesto de venta (ej. `ISV 15%`). Debe tener Código SAR. |
| `supplier_taxes_id` | No | Impuesto de compra (crédito fiscal DMC). |
| `aplica_retencion_isr` | No | `VERDADERO`/`FALSO`. Aplica retención ISR. |

> Si una empresa ZOLI controla DUCA, también puede importar:
> `requiere_control_duca`, `es_no_originario`, `porcentaje_dai_insumo`,
> `es_originario_tlc`, `codigo_sac`, `porcentaje_dai`.

### 12.3 Clientes / Contactos (`res.partner`)

Ruta: *Contactos → Importar* (o *Ventas → Clientes*).

| Columna | Obligatorio | Descripción / validación |
|---|---|---|
| `name` | Sí | Nombre o razón social. |
| `company_type` | Sí | `company` (empresa) o `person` (persona). |
| `vat` | Sí* | RTN de 13/14 dígitos. *El genérico Consumidor Final no lleva RTN. |
| `email` | No | Debe ser un correo válido. |
| `phone` | No | Teléfono. |
| `street` / `city` | No | Dirección. |
| `customer_rank` | No | `1` para marcar como cliente. |
| `tiene_exoneracion_sar` | No | `VERDADERO`/`FALSO`. Cliente exonerado. |
| `exoneracion_fecha_vencimiento` | No | `AAAA-MM-DD`. Requerido si está exonerado. |

> El RTN se valida (13/14 dígitos). Si está mal formado, corrígelo en el Excel y
> vuelve a importar. La validación de exoneración al facturar usa
> `exoneracion_fecha_vencimiento` (ver sección 7.4).

---

*Kenocia (Kenosis Company) · soporte: support@kenocia.com*
