# Gap Analysis — Metalmecánica × `kc_product_custom_specs_lot`

**Fecha:** 2026-06-03  
**Alcance:** Correo implementador (`Correo 1.txt`) + respuesta cliente (imágenes) + Excel `metalmecanica_catalogo_normalizado_odoo.xlsx` vs módulo Odoo 18 v18.0.2.0.0  
**Estado:** Análisis previo a implementación — sin cambios de código

---

## 1. Resumen ejecutivo

| Dimensión | Estado |
|-----------|--------|
| **Arquitectura de negocio** | Alineada — producto genérico + specs en venta + lote |
| **Modelo de datos Odoo** | Aplicable — el módulo cubre el 90% del flujo operativo |
| **Catálogo maestro (Excel)** | Importable con configuración — 16 productos, 12 atributos, 2.502 SKUs históricos |
| **Formato de códigos** | **Gap crítico** — 4 esquemas coexisten sin validación de inventario |
| **Precios (3 listas)** | **Gap mayor** — fuera del módulo actual |
| **Migración inventario inicial** | **Gap mayor** — sin script ni procedimiento definido |
| **Producción MRP** | **Gap futuro** — configurado pero no implementado |

### Veredicto

El módulo **es la base correcta** para implementar el escenario. Los gaps principales no invalidan el módulo: son **decisiones de negocio pendientes**, **carga de datos** y **2–3 extensiones puntuales de código** (nomenclatura de lote/SKU comercial).

---

## 2. Matriz de cobertura

| # | Requerimiento | Fuente | Módulo | Gap |
|---|---------------|--------|--------|-----|
| 1 | Productos genéricos sin variantes | Correo, Excel | `product.template` + atributos | Ninguno |
| 2 | Atributos técnicos reutilizables | Correo, Excel | `custom.technical.attribute` | Ninguno |
| 3 | Atributos distintos por familia | Correo, Excel | `custom.product.technical.attribute.line` | Ninguno |
| 4 | Valores permitidos por producto | Correo, Excel | `allowed_value_ids` | Ninguno |
| 5 | Captura en venta (modal) | Correo | `kc.sale.line.specs.wizard` | Ninguno |
| 6 | Clave técnica para matching | Correo, Excel | `technical_key` (pipe-separated) | Ninguno* |
| 7 | Lote por especificación | Correo | `stock.lot` + trazabilidad | Ninguno |
| 8 | Stock compatible por clave | Correo | `_search_compatible_lots()` | Ninguno |
| 9 | Validación en entrega | Correo | `stock.picking` + constraints | Ninguno |
| 10 | Cotizar sin lote / asignar al despachar | Correo | `kc_lot_policy = later` | Ninguno |
| 11 | Autorización PIN creación lote | Correo (implícito) | `kc.lot.creation.auth.wizard` | Ninguno |
| 12 | Specs en cotización/factura | Correo | `kc_invoice_detail_mode` + reportes | Configuración |
| 13 | Nombre de lote legible | Correo, Excel | `build_lot_name()` | **Gap código** |
| 14 | SKU comercial legacy | Excel, cliente | No existe | **Gap código/proceso** |
| 15 | Reglas SKU por tipo de pieza | Imagen catálogo cliente | No existe | **Gap código** |
| 16 | 3 listas de precios | Correo, Excel | No existe | **Gap otro módulo/proceso** |
| 17 | Cálculo precio por medida/calibre | Correo (futuro) | No existe | **Gap futuro** |
| 18 | Importación 2.502 SKUs → genéricos | Excel | No existe | **Gap script/datos** |
| 19 | Existencias iniciales por lote | Correo | Manual / import | **Gap procedimiento** |
| 20 | Creación lote desde MRP | Settings | `from_mrp` bloqueado | **Gap futuro** |
| 21 | Longitudes 10Ft / 12Ft | Cliente | Solo 8Ft en Excel | **Gap datos** |
| 22 | Calibres C22/C24 completos | Cliente | Parcial en Excel | **Gap datos** |

\*La clave técnica es compatible si los códigos de valor (`2`, `LG`, `C16`) se cargan igual en maestros y en importación.

---

## 3. Gaps por categoría

### 3.1 Sin código — solo configuración e importación

| ID | Gap | Acción recomendada | Responsable | Esfuerzo |
|----|-----|-------------------|-------------|----------|
| G-C01 | Crear 12 atributos técnicos | Importar desde hoja **Atributos** + **Valores Atributos** | Consultor | Medio |
| G-C02 | Crear 16 productos genéricos | Importar desde **Productos Base** con `default_code` = código base (BTELG, DPC, …) | Consultor | Bajo |
| G-C03 | Configurar atributos por producto | Mapear hoja **Atributos por Producto** → `technical_attribute_line_ids` | Consultor | Medio |
| G-C04 | Tracking por lote en todos los genéricos | Obligatorio — constraint del módulo | Consultor | Bajo |
| G-C05 | Valores permitidos por producto | Restringir según Excel (evita combinaciones inválidas) | Consultor | Alto |
| G-C06 | PIN en empleados autorizados | Configurar `hr.employee.pin` | Cliente RRHH | Bajo |
| G-C07 | Ajustes del módulo | Modal auto, cotizar sin lote, PIN obligatorio | Consultor + Cliente | Bajo |
| G-C08 | Modo detalle en documentos | `kc_invoice_detail_mode = technical` en productos metálicos | Consultor | Bajo |
| G-C09 | Completar longitudes 10Ft, 12Ft | Ampliar **Valores Atributos** según respuesta cliente | Cliente + Consultor | Bajo |
| G-C10 | Ampliar calibres C22, C24, C18 | Según catálogo comercial completo del cliente | Cliente | Bajo |

### 3.2 Proceso / decisión de negocio (bloqueantes)

| ID | Gap | Opciones | Impacto si no se decide |
|----|-----|----------|-------------------------|
| G-P01 | **Formato oficial de código comercial** | A) Mantener legacy (`BTELG24`) · B) Formato correo (`BTEL-12-8FT-C16-LG`) · C) Formato Excel (`BTELG-2-4-8FT-LG-C16`) | Documentos, precios e inventario inconsistentes |
| G-P02 | **Formato nombre de lote** | A) Compacto actual del módulo · B) Legible Excel · C) Híbrido (legible + correlativo) | Operarios de almacén no reconocen lotes |
| G-P03 | **Relación SKU legacy ↔ nuevo modelo** | ¿Campo referencia externa? ¿Tabla mapping? ¿Reemplazo total? | Imposible migrar 2.502 referencias de precio |
| G-P04 | **Política de lote en venta** | ¿Siempre exigir lote al confirmar? ¿Permitir `later` en todos los productos? | Flujo comercial distinto por familia |
| G-P05 | **Validación inventario** | Confirmar Alto vs Ancho en bandejas y reductores (nota Excel) | Errores en specs capturadas |
| G-P06 | **Estrategia de precios** | Tabla fija por combinación vs reglas vs manual | 2.502 filas sin precio en plantilla Excel |

### 3.3 Extensión de código (módulo actual)

| ID | Gap | Descripción | Prioridad | Complejidad |
|----|-----|-------------|-----------|-------------|
| G-D01 | Nomenclatura de lote legible | Override `build_lot_name()` → formato `BTELG-2-4-8FT-LG-C16-YYYYMMDD-####` | **Alta** | Baja |
| G-D02 | SKU comercial calculado | Campo computed `commercial_sku` con reglas por familia de producto | **Alta** | Media |
| G-D03 | Reglas SKU por tipo de pieza | Tramo: `{base}{ancho}-{long}` · Curva: `{base}{ancho}-{grado}` · Reductor: `{base}{mayor}{menor}` | **Alta** | Media-Alta |
| G-D04 | Campo referencia legacy | `legacy_sku` en lote/línea para mapeo BTELG24 ↔ specs | **Alta** | Baja |
| G-D05 | Secuencia por producto base | Correlativo `stock.lot.technical` global vs por familia | Media | Baja |
| G-D06 | Mostrar SKU comercial en PDF | Extender reportes venta/factura/albarán | Media | Baja |
| G-D07 | Import wizard catálogo | Script/wizard CSV desde Excel normalizado | **Alta** | Media |
| G-D08 | Import existencias iniciales | Cargar quants con lote + specs predefinidas | **Alta** | Media |
| G-D09 | Grados con sufijo G | Normalizar `45G` vs `45` en `_normalize_token` | Media | Baja |
| G-D10 | Integración MRP | Implementar `from_mrp` real | Baja (futuro) | Alta |

### 3.4 Fuera de alcance del módulo actual

| ID | Gap | Solución sugerida |
|----|-----|-------------------|
| G-O01 | 3 listas de precios (Detalle, Contratista, Distribuidor) | `product_pricelist` nativo + import CSV desde **Plantilla Precios** |
| G-O02 | Reglas de cálculo de precio (longitud, área, peso) | Módulo futuro de pricing o `sale` pricelist con fórmulas |
| G-O03 | Costeo / producción / planeación | MRP + módulo de costos (fase 2) |
| G-O04 | Catálogo e-commerce con 2.502 combinaciones | No usar variantes; buscador por atributos o asistente |

---

## 4. Comparativa de codificación (gap central)

### 4.1 Cuatro capas actuales

```
┌─────────────────────────────────────────────────────────────────────────┐
│ CAPA 1 — SKU LEGACY (histórico comercial)                               │
│ BTELG24 · CEHLG2490 · RECLG23634                                        │
│ Uso: listas de precio actuales, facturas históricas, almacén            │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↕ GAP: sin mapeo automático
┌─────────────────────────────────────────────────────────────────────────┐
│ CAPA 2 — SKU COMERCIAL PROPUESTO (correo / Excel / catálogo cliente)    │
│ BTEL-12-8FT-C16-GALV  ·  BTELG-2-4-8FT-LG-C16  ·  BTELG412-8           │
│ Uso: legibilidad comercial, cotizaciones, catálogo                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↕ GAP: no implementado
┌─────────────────────────────────────────────────────────────────────────┐
│ CAPA 3 — CLAVE TÉCNICA (matching inventario)                            │
│ ALTO=2|ANCHO=4|LONGITUD=8FT|LAMINA=LG|CALIBRE=C16                       │
│ Uso: buscar stock compatible, validar entrega                           │
│ Estado: IMPLEMENTADO en módulo ✓                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↕ GAP: formato distinto
┌─────────────────────────────────────────────────────────────────────────┐
│ CAPA 4 — NOMBRE DE LOTE (trazabilidad física)                           │
│ Módulo:  BTELG248FTLGC16_20260521_0001                                  │
│ Excel:   BTELG-2-4-8FT-LG-C16-20260526-0001                             │
│ Uso: etiqueta física, stock.lot.name                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Ejemplo concreto — Bandeja 2"×4"×8Ft LG C16

| Capa | Valor | ¿Existe hoy? |
|------|-------|--------------|
| Legacy | `BTELG24` | En Excel como SKU Original |
| Correo | `BTEL-4-8FT-C16-GALV` *(incompleto: falta alto, usa GALV)* | Propuesta no validada |
| Excel lote | `BTELG-2-4-8FT-LG-C16-20260526-0001` | Hoja Ejemplos Lotes |
| Catálogo cliente | `BTELG412-8` *(codifica ref base + ancho + longitud)* | Imagen catálogo |
| `technical_key` | `ALTO=2\|ANCHO=4\|LONGITUD=8FT\|LAMINA=LG\|CALIBRE=C16` | Excel + módulo ✓ |
| Lote módulo | `BTELG248FTLGC16_20260521_0001` | Código actual |

### 4.3 Reglas SKU por familia (imagen catálogo — no implementadas)

| Familia | Patrón aparente | Ejemplo |
|---------|-----------------|---------|
| Tramo recto | `{REF}{ANCHO}-{LONG}` | `BTELG412-8` |
| Curva horizontal | `{REF}{ANCHO}-{GRADO}` | `CHTELG412-90` |
| Curva vertical | `{REF}{ANCHO}-{GRADO}` | `CVITELG412-90` |
| Tee | `{REF}{ANCHO}-{GRADO}` | `TETELG412-90` |
| Reductor centrado | `{REF}{ANCHO}{ANCHO_MENOR}` | `RCTELG41210` |
| Brida / tapa | `{REF}{ANCHO}` | `BPTELG412` |

**Gap:** el mixin actual usa un algoritmo **único** (`build_lot_specs_compact`) sin discriminar por `product.template`.

---

## 5. Gap de datos — Excel vs respuesta cliente

### 5.1 Productos genéricos (16) — listos para Odoo

| Producto base | Código | SKUs históricos | Atributos |
|---------------|--------|-----------------|-----------|
| Bandeja Portacable Escalera | BTELG | 100 | Alto, Ancho, Longitud, Lámina, Calibre |
| Codo Ducto Cuadrado | CDC | 38 | Alto, Ancho, Lámina, Calibre, Grados |
| Curva Escalera Horizontal | CEHLG | 202 | Alto, Ancho, Lámina, Calibre, Grados |
| Curva Escalera Vertical Externa-Bajada | CEVELG | 200 | Alto, Ancho, Lámina, Calibre, Grados |
| Curva Escalera Vertical Interna-Subida | CEVILG | 200 | Alto, Ancho, Lámina, Calibre, Grados |
| Ducto Portacable Cuadrado | DPC | 23 | Alto, Ancho, Longitud, Lámina, Calibre |
| Jgo. Brida a Panel BTE | BPBTELG | 6 | Perfil, Lámina, Calibre |
| Reductor Escalera Centrado | RECLG | 816 | Alto, Ancho Mayor, Ancho Menor, Lámina, Calibre |
| Tapa Final BTE | TFBAL | 101 | Alto, Ancho, Lámina, Calibre |
| Tapadera Curva Escalera Horizontal | TCEHLGC | 96 | Alto, Ancho, Lámina, Calibre, Grados |
| Tapadera Curva Escalera Vertical Externa-Bajada | TCEVBLGC | 102 | Alto, Ancho, Lámina, Calibre, Grados |
| Tapadera Reductor Escalera Centrado | TRECLGC | 408 | Ancho Mayor, Ancho Menor, Lámina, Calibre |
| Tapadera Superior | TSLG | 53 | Ancho, Longitud, Lámina, Calibre |
| Tapadera Tee Escalera Horizontal | TTEHLGC | 48 | Alto, Ancho, Lámina, Calibre, Grados |
| Tee Escalera Horizontal | TEHLG | 101 | Alto, Ancho, Lámina, Calibre, Grados |
| Union BTE | UBTELG | 8 | Perfil, Lámina, Calibre, Cant. Tornillos, Tamaño Tornillo |

### 5.2 Atributos maestros (12)

| Atributo | Código Odoo | Tipo | Valores en Excel | Valores cliente (bandeja) |
|----------|-------------|------|------------------|----------------------------|
| Perfil | PERFIL | selection | 4 | — |
| Alto | ALTO | selection | 20 | 2", 4", 6" |
| Ancho | ANCHO | selection | 22 | 4" … 36" |
| Ancho Mayor | ANCHO_MAYOR | selection | 16 | — |
| Ancho Menor | ANCHO_MENOR | selection | 16 | — |
| Longitud | LONGITUD | selection | **1 (8Ft)** | 8, 10, 12 FT |
| Material/Lámina | LAMINA | selection | LG, AL | LG, AL |
| Calibre | CALIBRE | selection | 5 | C24, C22, C18, C16, C11 |
| Grados | GRADOS | selection | 45, 90 | 45G, 90G |
| Cantidad Tornillos | CANT_TORNILLOS | numeric | 2 | — |
| Tamaño Tornillo | TORNILLO | selection | 1 | — |

### 5.3 Gaps de catálogo detectados

| Gap datos | Detalle | Acción |
|-----------|---------|--------|
| **G-DAT01** | Longitud solo `8Ft` en 2.502 SKUs | Agregar 10Ft, 12Ft antes de go-live bandejas |
| **G-DAT02** | Calibres incompletos vs cliente | Validar catálogo comercial completo |
| **G-DAT03** | Grados sin sufijo `G` | Definir display (`45G`) vs código interno (`45`) |
| **G-DAT04** | Alto 2½" en ductos (`CDC2P5...`) | Valor `21-2` en Excel — validar normalización en clave |
| **G-DAT05** | Precios vacíos en plantilla | Cliente debe completar 2.502 × 3 listas |
| **G-DAT06** | 16 productos vs familias del correo | Correo simplificó; Excel es la fuente operativa correcta |

---

## 6. Matriz de migración SKU legacy → Odoo

### 6.1 Modelo objetivo

```text
product.template (16 genéricos)
    └── sale.order.line / stock.lot
            ├── technical_value_ids  (atributos desglosados)
            ├── technical_key        (matching)
            ├── legacy_sku           (GAP — campo a definir)
            └── commercial_sku       (GAP — campo a definir)
```

### 6.2 Ejemplos de descomposición (del Excel)

| SKU Original | Producto genérico | technical_key |
|--------------|-------------------|---------------|
| `BTELG24` | Bandeja Portacable Escalera | `ALTO=2\|ANCHO=4\|LONGITUD=8FT\|LAMINA=LG\|CALIBRE=C16` |
| `CDC2LGC2245` | Codo Ducto Cuadrado | `ALTO=2\|ANCHO=2\|LAMINA=LG\|CALIBRE=C22\|GRADOS=45` |
| `RECLG23634` | Reductor Escalera Centrado | `ALTO=2\|ANCHO_MAYOR=36\|ANCHO_MENOR=34\|LAMINA=LG\|CALIBRE=C16` |
| `UBTELG2` | Union BTE | `PERFIL=2\|LAMINA=LG\|CALIBRE=C16\|CANT_TORNILLOS=4\|TORNILLO=...` |

### 6.3 Estrategias de migración

| Estrategia | Pros | Contras | Recomendación |
|------------|------|---------|---------------|
| **A. Big bang** — 16 genéricos + import masivo lotes | Limpio, sin variantes | Alto esfuerzo inicial, riesgo operativo | Solo si inventario valida todo antes |
| **B. Por familia** — piloto BTELG + DPC | Riesgo controlado | Convivencia temporal dual | **Recomendado** |
| **C. Convivencia** — mantener SKU legacy como ref externa | No rompe precios actuales | Dos sistemas en paralelo | Transitorio 3–6 meses |
| **D. Solo ventas nuevas** — histórico congelado | Mínimo impacto | Reportes duplicados | No recomendado a largo plazo |

---

## 7. Plan de acción por fases

### Fase 0 — Decisiones (1 sesión con cliente)

- [ ] **D1:** Formato nombre de lote oficial
- [ ] **D2:** Formato SKU comercial visible en documentos
- [ ] **D3:** ¿Mantener referencia legacy (`BTELG24`) en sistema?
- [ ] **D4:** Política cotizar sin lote (global o por familia)
- [ ] **D5:** Validar Alto/Ancho con inventario (nota Excel)
- [ ] **D6:** Estrategia de precios (tabla fija vs manual)

### Fase 1 — Maestros (sin código)

- [ ] Instalar módulo + dependencia `hr`
- [ ] Importar 12 atributos + 92 valores (ampliar longitudes/calibres)
- [ ] Crear 16 `product.template` con tracking por lote
- [ ] Configurar matriz atributos por producto (76 líneas)
- [ ] Configurar PIN empleados + ajustes del módulo
- [ ] Piloto manual: 5 cotizaciones bandeja + 2 ductos

**Entregable:** catálogo operativo en Odoo sin migración masiva.

### Fase 2 — Extensiones código (según D1–D3)

| Si se decide… | Desarrollo |
|---------------|------------|
| Lote legible Excel | G-D01: override `build_lot_name()` |
| SKU comercial en docs | G-D02 + G-D03 + G-D06 |
| Mapping legacy | G-D04 + G-D07 import CSV |
| Existencias iniciales | G-D08 |

**Entregable:** nomenclatura alineada + importación catálogo.

### Fase 3 — Precios e inventario

- [ ] Cliente completa **Plantilla Precios**
- [ ] Import a 3 `product.pricelist` (por `technical_key` o SKU legacy temporal)
- [ ] Carga existencias iniciales con lotes técnicos
- [ ] Capacitación ventas + almacén

### Fase 4 — Futuro (opcional)

- [ ] Reglas de pricing automático
- [ ] Integración MRP (`from_mrp`)
- [ ] Costeo por calibre/lámina

---

## 8. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Operarios no reconocen lotes compactos | Alta | Alto | G-D01 antes de go-live |
| Precios desincronizados (2.502 refs) | Alta | Alto | Mapping legacy + import pricelist |
| Combinaciones inválidas en venta | Media | Medio | `allowed_value_ids` estricto |
| Confusión Alto/Ancho en bandeja | Media | Medio | Validación inventario (G-P05) |
| Clave técnica distinta por normalización | Baja | Alto | Usar códigos valor del Excel, no nombres display |
| Entrega bloqueada por lote incorrecto | Media | Medio | Capacitación + política `later` en transición |

---

## 9. Checklist de implementación Odoo

### Maestros

```
[ ] custom.technical.attribute × 12
[ ] custom.technical.attribute.value × ~95 (con ampliaciones)
[ ] product.template × 16 (default_code = BTELG, DPC, …)
[ ] custom.product.technical.attribute.line × 76
[ ] hr.employee.pin para autorizadores
[ ] ir.config_parameter (4 ajustes del módulo)
```

### Operación

```
[ ] Flujo venta: modal specs → lote existente / crear / later
[ ] Flujo entrega: validación lote vs technical_key
[ ] Flujo factura: kc_invoice_detail_mode = technical
[ ] Vista inventario: Existencias por lote y especificación
[ ] Reporte ficha técnica de lote
```

### Pendiente desarrollo

```
[ ] build_lot_name legible (G-D01)
[ ] commercial_sku por familia (G-D02, G-D03)
[ ] legacy_sku mapping (G-D04)
[ ] Wizard import Excel (G-D07)
[ ] Import existencias (G-D08)
[ ] Pricelist import (G-O01)
```

---

## 10. Decisiones requeridas — formulario para cliente

Completar antes de Fase 2:

| # | Pregunta | Opción A | Opción B | Opción C |
|---|----------|----------|----------|----------|
| 1 | Nombre de lote | Compacto actual | Legible Excel | Otro: _______ |
| 2 | SKU en cotización | Legacy (BTELG24) | Legible (BTELG-2-4-8FT-…) | Solo descripción técnica |
| 3 | Referencia legacy en sistema | Sí, campo aparte | No, solo nuevo esquema | Transitorio 6 meses |
| 4 | Cotizar sin lote | Permitido | No permitido | Solo algunas familias |
| 5 | Piloto inicial | Solo bandejas | Bandejas + ductos | Todas las familias |
| 6 | Precios iniciales | Import tabla fija | Manual en venta | Mantener Excel externo |

---

## 11. Conclusión

| Área | % cubierto por módulo actual | Acción |
|------|------------------------------|--------|
| Flujo venta–inventario–entrega | **~95%** | Configuración |
| Modelo de datos / atributos | **~100%** | Import Excel |
| Clave técnica (matching) | **~100%** | Import con códigos consistentes |
| Nomenclatura lote/SKU comercial | **~30%** | Extensión código (G-D01–D03) |
| Precios | **0%** | Pricelist nativo + import |
| Migración masiva | **0%** | Script import (G-D07, G-D08) |

**El módulo no necesita reemplazarse.** Necesita **configuración de maestros**, **decisiones de codificación** y **extensiones acotadas** en nomenclatura e importación.

---

## Referencias

- Documentación técnica: `DOCUMENTACION_TECNICA_FUNCIONAL.md`
- Correo implementador: `Correo 1.txt`
- Catálogo normalizado: `metalmecanica_catalogo_normalizado_odoo.xlsx`
- Módulo: `kc_product_custom_specs_lot` v18.0.2.0.0

---

*Documento generado para planificación de implementación — KENOCIA / Odoo 18*
