# Manual de Usuario — Kenocia Tesorería v18

> Tesorería empresarial para Odoo 18: cobros y pagos con correlativos bancarios,
> anticipos CXC/CXP, caja chica SAR, dispersión/pagos masivos y reportes.
>
> Módulo: `kenocia_tesoreria_v18` · Versión: `18.0.1.12.0` · Autor: Kenocia (Kenosis Company) · Licencia: LGPL-3.

Este manual cubre la operación diaria del módulo, **todas las opciones** disponibles
y, de forma destacada, las **afectaciones contables** (qué asiento genera cada
acción y contra qué cuentas). Está pensado para usuarios funcionales (tesorería,
contabilidad, custodios de caja) e implementadores.

---

## Índice

1. [Visión general y filosofía contable](#1-visión-general-y-filosofía-contable)
2. [Requisitos e instalación](#2-requisitos-e-instalación)
3. [Roles y permisos](#3-roles-y-permisos)
4. [Mapa de menús](#4-mapa-de-menús)
5. [Configuración inicial](#5-configuración-inicial)
   - [5.1 Cuentas de anticipo de la empresa](#51-cuentas-de-anticipo-de-la-empresa)
   - [5.2 Diarios de banco y caja](#52-diarios-de-banco-y-caja)
   - [5.3 Secuencias bancarias (correlativos)](#53-secuencias-bancarias-correlativos)
   - [5.4 Las tres numeraciones: SAR vs nativa vs Tesorería Kenocia](#54-las-tres-numeraciones-sar-vs-nativa-vs-tesorería-kenocia)
6. [Pagos y cobros de tesorería](#6-pagos-y-cobros-de-tesorería)
   - [6.1 Tipos de transacción y correlativo](#61-tipos-de-transacción-y-correlativo)
   - [6.2 Afectación contable del pago/cobro](#62-afectación-contable-del-pagocobro)
   - [6.3 Anulación de cheques](#63-anulación-de-cheques)
7. [Anticipos CXC / CXP](#7-anticipos-cxc--cxp)
   - [7.1 Crear y confirmar un anticipo](#71-crear-y-confirmar-un-anticipo)
   - [7.2 Aplicar el anticipo a una factura](#72-aplicar-el-anticipo-a-una-factura)
   - [7.3 Aplicación automática](#73-aplicación-automática)
   - [7.4 Cancelar / revertir](#74-cancelar--revertir)
8. [Caja chica](#8-caja-chica)
   - [8.1 Abrir el fondo](#81-abrir-el-fondo)
   - [8.2 Anticipos a empleados](#82-anticipos-a-empleados)
   - [8.3 Liquidación con factura SAR](#83-liquidación-con-factura-sar)
   - [8.4 Recarga del fondo](#84-recarga-del-fondo)
   - [8.5 Cierre del fondo (arqueo)](#85-cierre-del-fondo-arqueo)
9. [Dispersión y pagos masivos](#9-dispersión-y-pagos-masivos)
   - [9.1 Escenario 1: pago/cobro masivo de un contacto](#91-escenario-1-pagocobro-masivo-de-un-contacto)
   - [9.2 Escenario 2: dispersión a proveedores](#92-escenario-2-dispersión-a-proveedores)
   - [9.3 Escenario 3: dispersión de nómina](#93-escenario-3-dispersión-de-nómina)
   - [9.4 El lote y el archivo del banco (TXT)](#94-el-lote-y-el-archivo-del-banco-txt)
10. [Dashboard de tesorería](#10-dashboard-de-tesorería)
11. [Reportes](#11-reportes)
12. [Resumen de afectaciones contables](#12-resumen-de-afectaciones-contables)
13. [Preguntas frecuentes y solución de problemas](#13-preguntas-frecuentes-y-solución-de-problemas)

---

## 1. Visión general y filosofía contable

Kenocia Tesorería centraliza la operación de **cobros, pagos, anticipos y caja
chica** sobre la contabilidad **nativa** de Odoo 18.

Principios clave:

- **Contabilidad 100 % nativa.** Los pagos usan el motor estándar `account.payment`
  (cuentas *outstanding* / puente) y la **conciliación nativa**. El módulo **no
  inventa asientos** salvo en tres casos controlados: la *aplicación* de un
  anticipo a una factura, la *recarga* de caja chica y el *cierre* de caja chica.
- **Correlativos bancarios propios.** Cada combinación (diario, tipo de
  transacción) puede tener un correlativo con prefijo, padding y control de
  huecos por anulación (cheques que se "queman").
- **Sin cuentas "hardcodeadas".** Las cuentas de anticipo, puente, banco y caja se
  configuran; el módulo nunca asume números de cuenta.

> ℹ️ A lo largo del manual, **DEBE** = débito y **HABER** = crédito.

---

## 2. Requisitos e instalación

**Dependencias** (se instalan automáticamente): `account`, `account_accountant`,
`account_batch_payment`, `sale`, `purchase`, `mail`, `hr_payroll`,
`hr_payroll_account`, `kc_fiscal_hn_v18`.

No requiere librerías de Python adicionales.

Instalación: *Aplicaciones → buscar "Kenocia Tesorería" → Instalar*. Tras
instalar, asigne los roles a los usuarios (sección 3) y realice la configuración
inicial (sección 5).

> ⚠️ Versión: el módulo es para **Odoo 18**. No instalar sobre Odoo 19 (usa APIs
> que difieren entre versiones).

---

## 3. Roles y permisos

El módulo define cinco grupos bajo la categoría **"Tesorería Kenocia"**:

| Rol | Para qué sirve | Hereda de |
|---|---|---|
| **Tesorería CXC** | Cobros, adelantos de clientes y operaciones CXC. | Usuario interno |
| **Tesorería CXP** | Pagos, adelantos a proveedores, cheques y operaciones CXP. | Usuario interno |
| **Supervisor de Tesorería** | Todo lo de CXC + CXP, **anular cheques**, reportes globales y **cerrar fondos** de caja. | CXC + CXP |
| **Administrador de Tesorería** | Acceso total: **secuencias**, configuración y borrado. | Supervisor |
| **Custodio de Caja Chica** | Solo su(s) fondo(s) de caja chica: anticipos y liquidaciones. | Usuario interno |

Jerarquía efectiva: **Administrador ⊃ Supervisor ⊃ (CXC ∪ CXP)**. El **Custodio**
es independiente.

Herencias automáticas:
- *Ajustes / Administrador del sistema* ⇒ Administrador de Tesorería.
- *Responsable contable* (`account.group_account_manager`) ⇒ Supervisor de Tesorería.

**Controles de seguridad relevantes:**

- Un usuario **CXC** no puede registrar pagos salientes y un **CXP** no puede
  registrar cobros entrantes (se valida al crear/guardar el pago).
- El **Custodio** solo ve y opera **sus propios fondos** (donde es custodio) y
  los pagos ligados a anticipos de caja chica; no ve el resto de pagos ni las
  secuencias.
- Multicompañía: todos los registros respetan la(s) compañía(s) del usuario.

---

## 4. Mapa de menús

Menú raíz: **Tesorería**.

- **Dashboard** — panel de indicadores (sección 10).
- **Cobros CXC**
  - Cobros · Cheques · Transferencias · Efectivo (registro de `account.payment` entrantes)
  - **Cobro masivo** (Escenario 1)
  - **Adelantos de Clientes** (anticipos CXC)
- **Pagos CXP**
  - Pagos · Cheques · Transferencias · Efectivo (registro de `account.payment` salientes)
  - **Pago masivo** (Escenario 1)
  - **Dispersión a proveedores** (Escenario 2)
  - **Dispersión de nómina** (Escenario 3)
  - **Adelantos a Proveedores** (anticipos CXP)
  - **Recargas Caja Chica**
- **Caja Chica**
  - **Fondos** · **Anticipos**
- **Reportes**
  - Reportes de tesorería · **Caja Chica** (reportes operativo y fiscal SAR)
- **Configuración** *(solo Supervisor/Administrador)*
  - **Secuencias Bancarias** · **Diarios banco y caja** · **Cuentas banco y efectivo** · **Cuentas de anticipo** · **Conciliación manual**

---

## 5. Configuración inicial

### 5.1 Cuentas de anticipo de la empresa

*Tesorería → Configuración → Cuentas de anticipo* (o en la ficha de la compañía).

| Campo | Tipo de cuenta exigido | Significado contable |
|---|---|---|
| **Cuenta anticipos clientes (CXC)** | **Pasivo** (`liability_current` / `liability_payable`) | El cliente paga por adelantado → la empresa queda **obligada** a entregar el bien/servicio (es un pasivo). Ej. `2090101 Anticipos de clientes`. |
| **Cuenta anticipos proveedores (CXP)** | **Activo** (`asset_current` / `asset_receivable` / `asset_prepayments`) | La empresa paga por adelantado → tiene un **derecho** a recibir (es un activo). |

> ✅ Ambas cuentas deben tener **"Permitir conciliación"** activado.

### 5.2 Diarios de banco y caja

*Tesorería → Configuración → Diarios banco y caja*.

En cada diario de banco/caja encontrará la pestaña **"Tesorería Kenocia"** con:

- **Formato dispersión banco**: formato del TXT (BAC, Atlántida, Ficohsa,
  Banpaís, Davivienda) que usará el lote de dispersión. *El formato va ligado al
  diario*: no se puede elegir un formato de un banco distinto al del diario.
- **Secuencias de tesorería** del diario (sección 5.3) con botón *Nueva secuencia*.

Avisos automáticos del diario:
- Si algún método de pago no tiene **cuenta de pagos pendientes (outstanding)**,
  aparece una alerta (los pagos podrían quedar sin asiento).
- Si el diario tiene **"Secuencia de pago dedicada"** nativa **y** una secuencia
  Kenocia de cheque, aparece una nota: los cheques se numerarán con el
  **correlativo Kenocia** (no con la serie `PAY` nativa). Es una coexistencia
  válida.

### 5.3 Secuencias bancarias (correlativos)

*Tesorería → Configuración → Secuencias Bancarias* (solo Administrador puede crear/editar).

Una secuencia define el **correlativo** de un tipo de documento en un diario.

| Campo | Descripción |
|---|---|
| **Nombre** | Identificación de la secuencia. |
| **Diario** | Diario de banco o caja al que aplica. |
| **Tipo de transacción** | Cheque, Depósito, Débito, Crédito, Transferencia, Transferencia Bancaria, Efectivo. |
| **Prefijo** | Texto antepuesto. Ej. `CHQ/BCO/2026/`. |
| **Próximo número** | Siguiente correlativo a emitir. |
| **Dígitos (padding)** | Relleno con ceros (1–12). Ej. padding 4 → `0001`. |
| **Activo** | Si está apagada, no se usa. |
| **Vista previa** | Muestra cómo quedará el próximo número. |
| **Último número emitido / Huecos por anulación** | Trazabilidad (solo lectura). |

Reglas importantes:
- **Una sola secuencia por (diario, tipo).**
- **Anti-duplicados**: al emitir un número se toma un *bloqueo atómico*; si dos
  usuarios emiten a la vez, uno recibe el aviso *"Otro usuario está generando un
  número…"* y reintenta.
- **No hay correlativo obligatorio**: si un pago de tesorería no encuentra una
  secuencia activa para su (diario, tipo), usa la **numeración nativa de Odoo** y
  **no se bloquea**.

> ⚠️ La secuencia de tesorería se consume **solo** cuando el pago/cobro lleva un
> **"Tipo tesorería"** que coincide con el tipo de la secuencia. Los flujos
> automáticos de **caja chica** (liquidación y recarga) **no** asignan tipo de
> tesorería, por lo que usan numeración nativa, no el correlativo Kenocia.

### 5.4 Las tres numeraciones: SAR vs nativa vs Tesorería Kenocia

Es fundamental no confundir las tres numeraciones que conviven en Odoo:

| Numeración | Dónde aplica | ¿Obligatoria? | Qué controla |
|---|---|---|---|
| **SAR / CAI** (fiscal HN) | Diarios de **ventas** y **compras** (facturas, NC/ND) | **Sí** (exigencia fiscal) | Comprobantes timbrados autorizados por la SAR (CAI, correlativo, rango, vencimiento) |
| **Nativa de Odoo** (código del diario + secuencia del asiento) | **Todos** los diarios, incluidos banco y efectivo | Automática | Nombre/consecutivo del asiento contable |
| **Tesorería Kenocia** (`kenocia.sequence`) | Banco/efectivo, por tipo (cheque, depósito, transferencia, efectivo…) | **Opcional** | Control interno de chequera / depósitos / dispersión |

Puntos clave:

- **Los diarios de banco y efectivo NO llevan numeración SAR/CAI.** El CAI es para
  documentos timbrados (facturas y notas); un cheque, una transferencia, un
  depósito o un recibo de pago **no** son comprobantes fiscales con CAI. El módulo
  fiscal excluye por diseño los pagos y las líneas de extracto bancario.
- Por eso la sección **"Numeración SAR"** de la ficha del diario **solo se muestra
  en diarios de ventas y compras**; en banco/efectivo no aparece.
- El control fiscal de un gasto pagado en efectivo recae en la **factura del
  proveedor** (su CAI/correlativo/RTN), que la liquidación de caja chica valida —
  no en el diario de efectivo.

---

## 6. Pagos y cobros de tesorería

Los pagos y cobros se registran desde *Cobros CXC* o *Pagos CXP* (Cheques,
Transferencias, Efectivo, etc.). Son `account.payment` nativos con campos extra
de Kenocia.

### 6.1 Tipos de transacción y correlativo

El campo **Tipo tesorería** (cheque, depósito, débito, crédito, transferencia,
transferencia bancaria, efectivo) activa el correlativo Kenocia al **confirmar**:

1. Al confirmar, si existe una **secuencia activa** para (diario, tipo), se
   consume un correlativo y se guarda en **Correlativo tesorería**; además, ese
   número **renombra el asiento** del pago.
2. Si **no** existe secuencia, el pago se numera con la secuencia **nativa** del
   diario (sin bloqueo).
3. **Idempotente**: si el pago se regresa a borrador y se vuelve a publicar,
   **conserva** su correlativo (no quema un número nuevo).

Campos de control visibles: **Correlativo tesorería**, **Estado tesorería**
(Borrador / Publicado / Conciliado / Anulado / Cancelado) y **Monto en letras**.

### 6.2 Afectación contable del pago/cobro

El asiento lo genera el **motor nativo** de `account.payment` (cuentas
*outstanding*):

- **Cobro CXC (entrante):**
  - DEBE *Cuenta de pagos pendientes a recibir* (outstanding/banco transitorio)
  - HABER *Cuenta destino* (CxC del cliente, o cuenta de anticipo si es anticipo)
- **Pago CXP (saliente):**
  - DEBE *Cuenta destino* (CxP del proveedor, o cuenta de anticipo)
  - HABER *Cuenta de pagos pendientes a pagar* (outstanding/banco transitorio)

Al conciliar el pago contra el extracto bancario, la cuenta *outstanding* se
salda contra la cuenta de liquidez (banco). Si al diario le falta la cuenta
*outstanding*, el módulo la asigna automáticamente desde el método de pago.

### 6.3 Anulación de cheques

Disponible solo para pagos de **tipo Cheque** y solo para **Supervisor/Administrador**.

1. En el cheque, botón **"Anular Cheque"** (visible en borrador/publicado/pagado).
2. Se abre el asistente: ingrese el **motivo** (obligatorio).
3. Al confirmar:
   - El correlativo del cheque se registra como **hueco** (`Huecos por anulación`)
     y **nunca se reutiliza**.
   - Si el cheque ya estaba publicado, se ejecuta la **cancelación contable
     nativa** del pago (revierte/cancela el asiento).
   - El cheque queda marcado como **Anulado** con su motivo en el chatter.

> El aviso nativo de "secuencia no consecutiva" en la serie del diario es
> esperado: refleja el número quemado del cheque.

---

## 7. Anticipos CXC / CXP

*Cobros CXC → Adelantos de Clientes* o *Pagos CXP → Adelantos a Proveedores*.

Un anticipo registra dinero recibido/pagado **antes** de la factura, y luego se
**aplica** a una o varias facturas vía conciliación nativa.

### 7.1 Crear y confirmar un anticipo

Campos principales: **Tipo** (cliente/proveedor), **Contacto**, **Orden de
venta/compra** (opcional, excluyentes entre sí), **Diario de pago**, **Cuenta de
anticipo** (se precarga desde la configuración de la empresa) y **Monto**.

Validaciones: monto positivo; la cuenta de anticipo debe ser conciliable; si se
liga a una orden, el monto no puede superar el total de la orden y el
tipo/contacto deben ser coherentes.

Al pulsar **Confirmar**, se asigna la referencia (`ADEL-CXC-aaaa-####` /
`ADEL-CXP-aaaa-####`) y se crea y publica un `account.payment` cuyo **destino es
la cuenta de anticipo**.

**Afectación contable del anticipo:**

- **CXC (cliente paga por adelantado):**
  - DEBE *Banco / outstanding entrante*
  - HABER **Cuenta anticipos clientes (PASIVO)**
- **CXP (pago anticipado a proveedor):**
  - DEBE **Cuenta anticipos proveedores (ACTIVO)**
  - HABER *Banco / outstanding saliente*

### 7.2 Aplicar el anticipo a una factura

Desde la factura: botón **"Aplicar adelantos"** (factura publicada), o
automáticamente al publicar (sección 7.3). Se elige cuánto aplicar de cada
anticipo disponible (hasta el saldo del anticipo y el saldo de la factura).

Al aplicar, se crea un **asiento en el diario misceláneo (general)**:

- **CXC:** DEBE **Cuenta de anticipo (pasivo)** · HABER **CxC de la factura**
- **CXP:** DEBE **CxP de la factura** · HABER **Cuenta de anticipo (activo)**

Ese asiento se **concilia** con la línea por cobrar/pagar de la factura, de modo
que la factura queda saldada por el importe aplicado. El anticipo actualiza su
**saldo disponible** y su estado (*Parcialmente aplicado* / *Totalmente
aplicado*).

> Efecto neto: el saldo del anticipo (pasivo CXC / activo CXP) se "consume"
> contra la cuenta real por cobrar/pagar de la factura.

### 7.3 Aplicación automática

Al **publicar una factura**, el módulo busca anticipos elegibles del mismo
contacto, mismo tipo y misma moneda (priorizando los ligados a la orden de la
factura) y los aplica automáticamente hasta agotar el saldo de la factura o de
los anticipos.

### 7.4 Cancelar / revertir

- **Cancelar anticipo**: solo si **no** tiene aplicaciones; cancela el pago y deja
  el anticipo en *Cancelado*.
- **Volver a borrador**: solo desde *Confirmado* y sin aplicaciones.

En las órdenes de venta/compra se muestran además: **Total anticipado**, **Saldo
anticipos** y **Total a cobrar/pagar** (neto de anticipos).

---

## 8. Caja chica

Flujo: **abrir fondo → entregar anticipos a empleados → liquidar con factura →
recargar → cerrar (arqueo)**.

> Clave contable: la **entrega física** de efectivo a un empleado **no genera
> asiento**. El impacto contable real ocurre en la **liquidación** (cuando hay
> factura). Las **recargas** y el **cierre** sí generan asientos.

### 8.1 Abrir el fondo

*Caja Chica → Fondos → Crear*. Campos: **Diario de caja** (tipo efectivo),
**Cuenta puente (tránsito)** (pasivo, conciliable), **Custodio**, **Vigencia**
(desde/hasta) y **Monto autorizado**.

Al pulsar **Abrir fondo** (requiere Custodio/Supervisor/Administrador), el fondo
pasa a *Abierto*. La apertura **no genera asiento** (es una autorización del
fondo).

### 8.2 Anticipos a empleados

Desde el fondo, registre un **anticipo**: empleado, concepto y monto (no puede
superar el disponible del fondo).

Al **Confirmar entrega**, el estado pasa a *Entregado*. **No hay asiento
contable** — es la salida física del efectivo de la caja, que se controla
operativamente y se contabiliza al liquidar.

### 8.3 Liquidación con factura SAR

Cuando el empleado regresa con la **factura del proveedor**, se liquida el
anticipo (*Liquidar con factura*). El asistente valida el **cumplimiento fiscal
SAR** (RTN del proveedor, CAI, correlativo, clase de documento, etc., según la
configuración fiscal de la empresa).

Al **Confirmar liquidación**:

1. Se crea un `account.payment` **saliente** desde el **diario de caja del fondo**
   por el total de la factura, ligado al anticipo.
   - **Asiento:** DEBE **CxP del proveedor** · HABER **Cuenta de caja del fondo**.
2. Se **concilia** el pago con la factura → la factura del proveedor queda
   **pagada** desde la caja chica.
3. El **vuelto** (anticipo − total factura) regresa al fondo e incrementa el
   **disponible**.
4. El anticipo pasa a *Liquidado* con su factura, pago y fecha.

### 8.4 Recarga del fondo

*Pagos CXP → Recargas Caja Chica* (o desde el fondo). Repone efectivo al fondo en
**dos pasos**, usando la **cuenta puente** como tránsito:

1. **Enviar a tránsito** (Supervisor/Admin/CXP): crea un pago desde el **banco
   origen** hacia la **cuenta puente**.
   - **Asiento:** DEBE **Cuenta puente (tránsito)** · HABER **Cuenta bancaria**.
   - Estado *En tránsito*.
2. **Confirmar efectivo recibido** (Custodio): registra la entrada del efectivo a
   la caja.
   - **Asiento:** DEBE **Cuenta de caja del fondo** · HABER **Cuenta puente**.
   - Estado *Recibido* → suma al disponible del fondo.

> El esquema en dos pasos con cuenta puente permite controlar el dinero "en
> camino" entre el banco y la caja física.

### 8.5 Cierre del fondo (arqueo)

*Fondo → Cerrar fondo* (Supervisor/Admin). Requiere que no haya recargas en
tránsito ni anticipos entregados sin liquidar.

El asistente pide el **saldo físico contado** y el **banco donde depositar** el
remanente. Calcula la **diferencia de arqueo** (sobrante/faltante, informativa).

Al confirmar, si el saldo según sistema es positivo, se genera el asiento de
devolución:

- **Asiento de cierre:** DEBE **Cuenta bancaria de devolución** · HABER **Cuenta
  de caja del fondo** (por el saldo del sistema).

El fondo queda *Cerrado* con el arqueo registrado (físico, diferencia, banco,
usuario, fecha).

---

## 9. Dispersión y pagos masivos

Tres escenarios sobre un **motor común** que crea **un pago por beneficiario** y
concilia parcialmente por el **monto exacto** de cada documento.

> Modelo de numeración (**Opción A — "1 depósito = 1 correlativo"**): los pagos
> individuales usan **numeración nativa**; el **lote** recibe **un** correlativo
> Kenocia (tipo *Transferencia Bancaria*) si el diario tiene esa secuencia activa.

### 9.1 Escenario 1: pago/cobro masivo de un contacto

*Cobros CXC → Cobro masivo* o *Pagos CXP → Pago masivo*.

Un **único contacto**, un **único pago**, contra **varias facturas** con monto
parcial editable por línea.

Pasos: elija contacto y diario (y opcionalmente **Tipo tesorería** para
correlativo); se cargan las facturas abiertas; ajuste el **monto a pagar** por
línea; **Confirmar**.

**Afectación contable:** un solo `account.payment` que salda parcialmente las
facturas seleccionadas (conciliación parcial). Asiento nativo según
entrante/saliente (sección 6.2). *No* se agrupa en lote.

### 9.2 Escenario 2: dispersión a proveedores

*Pagos CXP → Dispersión a proveedores*.

Un **depósito** al banco que dispersa a **varios proveedores**. Pasos: elija el
**diario de banco** (define el **formato del banco**), la **fecha de depósito** y,
opcionalmente, filtre proveedores; **cargue facturas**; ajuste montos;
**Confirmar**.

Validaciones: todos los proveedores deben tener **cuenta bancaria** registrada.

**Afectación contable:** un `account.payment` **saliente por proveedor** (DEBE
CxP / HABER outstanding), cada uno conciliado parcialmente contra sus facturas.
Los pagos se agrupan en un **lote** (`account.batch.payment`) marcado como origen
*Proveedores*, que recibe el **correlativo Kenocia único** de la dispersión.

### 9.3 Escenario 3: dispersión de nómina

*Pagos CXP → Dispersión de nómina*.

Paga el **neto** de un **lote de nómina** aprobado, un pago por empleado. Pasos:
elija el **lote de nómina** (en estado cerrado/pagado), el **diario de banco** y
la **fecha**; **Confirmar**.

Requisitos: nómina aprobada con asiento publicado; cada empleado debe tener
**cuenta bancaria** y líneas contables por pagar.

**Afectación contable:** un `account.payment` por empleado que **concilia el neto
por pagar** de su nómina; se agrupan en lote (origen *Nómina*) con correlativo
único. Los recibos (`payslips`) se marcan como **pagados**.

### 9.4 El lote y el archivo del banco (TXT)

En el **lote de pagos** (`account.batch.payment`) verá:

- **Origen dispersión** (Proveedores / Nómina / Manual), **Correlativo
  dispersión** y **Formato de dispersión** (heredado del diario).
- Botón **"Generar archivo banco"**: produce el TXT para subir al banco.

> ⚠️ **Fase 2 (pendiente):** los generadores TXT por banco aún no están
> implementados. Al pulsar el botón, si el formato no tiene generador, se muestra
> el aviso de que falta configurarlo. Cuando el banco entregue su *layout*, se
> añade el generador correspondiente y queda operativo sin más cambios.

---

## 10. Dashboard de tesorería

*Tesorería → Dashboard*. Panel con filtros por compañía, fechas, diarios y fondos.
Muestra:

- **Bancos** y **Efectivo**: saldos contables reales por diario, con totales.
- **Liquidez unificada**: gráfica de bancos + efectivo.
- **Caja chica**: por fondo — disponible, autorizado, recargas, pendiente, % de
  uso y saldo contable; totales y fondos abiertos.
- **CXC**: cartera por cobrar con *aging* (corriente / advertencia 1–60 / crítico
  >60 días) y top 5 más atrasadas.
- **CXP**: cuentas por pagar (corriente / por vencer ≤7 días / vencido) y top 5.
- **Flujo de caja**: proyección a 4 semanas (2 reales + 2 futuras) con entradas,
  salidas y neto.
- **Alertas**: CXP vencido, CXC crítica y caja chica con anticipos sin factura SAR.

---

## 11. Reportes

### Reportes de tesorería

*Tesorería → Reportes*. Elija **tipo** (Operaciones de Tesorería o Adelantos
CXC/CXP), rango de fechas y diarios. Salidas:

- **PDF**: tabla de pagos (Fecha, Número, Tipo, Contacto, Diario, Monto, Estado,
  Conciliado) o de adelantos (Referencia, Fecha, Tipo, Contacto, Diario, Monto,
  Aplicado, Saldo, Estado).
- **CSV** (delimitado por `;`, UTF-8) con las mismas columnas.

### Reportes de caja chica

*Tesorería → Reportes → Caja Chica* (Supervisor/Admin). Dos tipos:

- **Operativo**: por fondo — resumen (Autorizado, Recargas, Entregado, Liquidado,
  Pendiente, Disponible) y detalle de anticipos y recargas del período.
- **Fiscal SAR**: anticipos liquidados con factura — datos fiscales del proveedor
  (RTN, CAI, correlativo, fecha de emisión, clase SAR, base, ISV, total) y total
  de **ISV acreditable**.

Ambos disponibles en **PDF** y **CSV**.

---

## 12. Resumen de afectaciones contables

| Acción | DEBE | HABER | Notas |
|---|---|---|---|
| **Cobro CXC** | Outstanding entrante / Banco | CxC del cliente | Asiento nativo del pago. |
| **Pago CXP** | CxP del proveedor | Outstanding saliente / Banco | Asiento nativo del pago. |
| **Anticipo CXC (confirmar)** | Banco / Outstanding | **Anticipos clientes (pasivo)** | Destino = cuenta de anticipo. |
| **Anticipo CXP (confirmar)** | **Anticipos proveedores (activo)** | Banco / Outstanding | Destino = cuenta de anticipo. |
| **Aplicar anticipo CXC** | Anticipos clientes (pasivo) | CxC de la factura | Asiento en diario general + conciliación. |
| **Aplicar anticipo CXP** | CxP de la factura | Anticipos proveedores (activo) | Asiento en diario general + conciliación. |
| **Anular cheque** | (reversa nativa) | (reversa nativa) | Cancela el asiento; correlativo "quemado". |
| **Caja: entregar anticipo** | — | — | **Sin asiento** (entrega física). |
| **Caja: liquidar con factura** | CxP del proveedor | Caja del fondo | + conciliación con la factura. |
| **Caja: recarga (paso 1)** | Cuenta puente | Banco origen | Banco → tránsito. |
| **Caja: recarga (paso 2)** | Caja del fondo | Cuenta puente | Tránsito → caja. |
| **Caja: cierre** | Banco de devolución | Caja del fondo | Por el saldo según sistema. |
| **Dispersión (por beneficiario)** | CxP del proveedor / empleado | Outstanding saliente | + conciliación parcial; lote con correlativo. |

---

## 13. Preguntas frecuentes y solución de problemas

**No aparece el correlativo Kenocia en mi pago.**
No hay una secuencia activa para ese (diario, tipo). El pago usa la numeración
nativa (es válido). Cree la secuencia en *Configuración → Secuencias Bancarias*
si quiere correlativo propio.

**La cuenta de anticipo de cliente me aparece como activo y no la encuentro.**
La cuenta de anticipos de clientes es de **pasivo**. Verifique que la cuenta sea
`liability_current`/`liability_payable` y que tenga conciliación activada.

**"Otro usuario está generando un número…".**
Es el control anti-duplicados de correlativos. Reintente en unos segundos.

**El botón "Generar archivo banco" muestra que el formato no está configurado.**
Es la Fase 2: el generador TXT de ese banco aún no está implementado. Comparta el
*layout* del banco para habilitarlo.

**Un proveedor/empleado no entra en la dispersión.**
Debe tener **cuenta bancaria** registrada (y, en nómina, líneas contables por
pagar). Regístrela y vuelva a cargar.

**No puedo cerrar el fondo de caja.**
No debe haber recargas *en tránsito* ni anticipos *entregados* sin liquidar.
Liquide o cancele esos movimientos primero.

**Cambié código Python y no veo el efecto.**
Los cambios de Python requieren **reiniciar el servicio de Odoo**. Actualizar el
módulo desde la interfaz no recarga el código Python.

---

> © Kenocia (Kenosis Company) · Licencia LGPL-3 · Soporte: consultoria@kenocia.com
