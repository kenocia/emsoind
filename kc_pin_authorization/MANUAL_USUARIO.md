# Manual de Usuario — KC Autorización por PIN

> Autorización por PIN de empleado, configurable, antes de validar documentos.
> Módulo núcleo: `kc_pin_authorization` · Autor: Kenocia (Kenosis Company) · Licencia: LGPL-3.

Este manual cubre la instalación, configuración y uso diario de la **familia de
módulos de Autorización por PIN**: el motor central y sus puentes con Inventario,
Ventas, Compras y Contabilidad.

---

## Índice

1. [Visión general](#1-visión-general)
2. [Arquitectura: núcleo + puentes](#2-arquitectura-núcleo--puentes)
3. [Requisitos e instalación](#3-requisitos-e-instalación)
4. [Roles y permisos](#4-roles-y-permisos)
5. [Mapa de menús](#5-mapa-de-menús)
6. [Preparación: PIN de los empleados](#6-preparación-pin-de-los-empleados)
7. [Configuración de reglas](#7-configuración-de-reglas)
   - [7.1 Crear una regla](#71-crear-una-regla)
   - [7.2 El filtro (dominio) para sub-operaciones](#72-el-filtro-dominio-para-sub-operaciones)
   - [7.3 Ejemplos por módulo](#73-ejemplos-por-módulo)
8. [Operación diaria: cómo se ve el PIN](#8-operación-diaria-cómo-se-ve-el-pin)
9. [Trazabilidad: campos, chatter y auditoría](#9-trazabilidad-campos-chatter-y-auditoría)
10. [Uso en reportes QWeb](#10-uso-en-reportes-qweb)
11. [Seguridad: bloqueo por intentos](#11-seguridad-bloqueo-por-intentos)
12. [Preguntas frecuentes y solución de problemas](#12-preguntas-frecuentes-y-solución-de-problemas)
13. [Clasificación para Implementadores](#13-clasificación-para-implementadores)

---

## 1. Visión general

La funcionalidad exige que **un empleado autorice una acción introduciendo su
PIN** antes de que un documento se valide/confirme/publique. Por ejemplo, antes
de validar una recepción de inventario o de confirmar un pedido de venta.

Características:

- **Configurable sin programar**: usted decide en qué documento y operación se
  pide el PIN desde *Ajustes*.
- **Diálogo con teclado numérico** que bloquea el fondo de la pantalla.
- **Rastro completo**: empleado que autorizó, fecha y hora, mensaje en el chatter
  del documento y registro en un log central de auditoría.
- **Seguro**: comparación de PIN protegida y bloqueo temporal tras varios
  intentos fallidos.

---

## 2. Arquitectura: núcleo + puentes

Es una familia de módulos. Instale el núcleo más el puente de cada app que quiera
proteger.

| Módulo | Rol | Documento | Operación |
|---|---|---|---|
| `kc_pin_authorization` | **Núcleo** (motor, reglas, diálogo, auditoría) | — | — |
| `kc_pin_authorization_stock` | Puente Inventario | `stock.picking` (transferencias) | Validar |
| `kc_pin_authorization_sale` | Puente Ventas | `sale.order` (pedidos) | Confirmar |
| `kc_pin_authorization_purchase` | Puente Compras | `purchase.order` (órdenes) | Confirmar |
| `kc_pin_authorization_account` | Puente Contabilidad | `account.move` (asientos/facturas) | Publicar |

> Cada puente arrastra automáticamente el núcleo como dependencia.

---

## 3. Requisitos e instalación

| Requisito | Detalle |
|---|---|
| Versión Odoo | 18.0 |
| Núcleo depende de | `mail`, `hr` |
| Puentes dependen de | su app respectiva (`stock`, `sale`, `purchase`, `account`) + núcleo |

**Instalación:** active el modo desarrollador → *Aplicaciones* → instale
"KC Autorización por PIN" y los puentes que necesite (Inventario, Ventas,
Compras, Contabilidad).

Por línea de comandos:

```bash
odoo -d <base> -i kc_pin_authorization_stock,kc_pin_authorization_sale,kc_pin_authorization_purchase,kc_pin_authorization_account --stop-after-init
```

---

## 4. Roles y permisos

| Grupo | Para qué sirve |
|---|---|
| Usuario interno (`base.group_user`) | Puede ser solicitado por el diálogo de PIN y consultar (lectura) las reglas. |
| Administrador del sistema (`base.group_system`) | Crea y edita las reglas, y consulta la auditoría. |
| Empleados **con PIN configurado** | Son los únicos que pueden autorizar (ver sección 6). |

> No hace falta que el empleado que autoriza sea el usuario que opera Odoo: el
> operador llama la acción y un supervisor (con su PIN) la autoriza en el mismo
> equipo.

---

## 5. Mapa de menús

*Ajustes ▸ Autorización por PIN*

- **Reglas** — definir dónde se exige el PIN.
- **Auditoría** — historial de autorizaciones (exitosas y fallidas).

También accesible desde *Ajustes ▸ (pestaña) Autorización por PIN* con los
botones **Configurar reglas** y **Ver auditoría**.

---

## 6. Preparación: PIN de los empleados

El PIN es el mismo campo que usa el Punto de Venta de Odoo.

1. Vaya a *Empleados* → abra la ficha del empleado.
2. Pestaña *Información de RR. HH.* (HR Settings) → campo **PIN**.
3. Escriba un PIN numérico y guarde.

Solo los empleados con PIN aparecerán como opción en el diálogo de autorización.

### 6.1 Que cada quien cambie su propio PIN (autogestión)

Para no depender de RR. HH., cada persona puede fijar/cambiar su propio PIN:

- **Usuario interno (backend)**: en *Preferencias* (menú de usuario, arriba a la
  derecha ▸ *Preferencias / Mi perfil*), pestaña *Preferencias*, sección
  **PIN de autorización**. Escriba el nuevo PIN y su confirmación y guarde.
- **Usuario de portal**: si la persona solo tiene acceso al portal, en
  *Mi cuenta* aparece la tarjeta **"Cambiar mi PIN"** (página `/my/pin`).
  Requiere el módulo `kc_pin_authorization_portal`.

Reglas en ambos casos: el PIN es **numérico, mínimo 4 dígitos**, y se aplica a
todos los empleados vinculados al usuario. Por privacidad, el PIN actual nunca
se muestra; solo se puede sobrescribir.

---

## 7. Configuración de reglas

Una **regla** indica: en qué documento, en qué operación y (opcionalmente) bajo
qué condición se exige el PIN. Sin una regla activa, **no se pide nada** y los
documentos funcionan normal.

### 7.1 Crear una regla

*Ajustes ▸ Autorización por PIN ▸ Reglas ▸ Nuevo*

| Campo | Qué poner |
|---|---|
| **Documento** | El modelo a proteger (p. ej. *Transferencia* = `stock.picking`). |
| **Operación** | El punto de acción: Validar / Confirmar / Publicar / Cancelar / Hecho. |
| **Filtro (dominio)** | Opcional. Acota a un sub-tipo (ver 7.2). Vacío = aplica a todos. |
| **Motivo** | Texto que verá el usuario y que queda en el chatter y la auditoría. |
| **Compañía** | Déjelo vacío para todas, o fíjelo a una compañía. |
| **Activa** | Desactívela para suspender la regla sin borrarla. |

> La **Operación** debe coincidir con la que usa el puente. Para los puentes
> incluidos: Inventario = *Validar*, Ventas = *Confirmar*, Compras = *Confirmar*,
> Contabilidad = *Publicar*.

### 7.2 El filtro (dominio) para sub-operaciones

En Odoo, "recepción" y "despacho" no son documentos distintos: son tipos de la
misma transferencia. El **filtro** permite distinguirlos.

| Caso | Dominio |
|---|---|
| Solo recepciones | `[("picking_type_code", "=", "incoming")]` |
| Solo despachos | `[("picking_type_code", "=", "outgoing")]` |
| Solo transferencias internas | `[("picking_type_code", "=", "internal")]` |
| Solo facturas de cliente | `[("move_type", "=", "out_invoice")]` |
| Pedidos por encima de un monto | `[("amount_total", ">", 50000)]` |

Puede usar el editor visual de dominio (el campo lo trae integrado) en lugar de
escribir el texto a mano.

### 7.3 Ejemplos por módulo

- **Inventario – Recepción**: Documento *Transferencia*, Operación *Validar*,
  Filtro `[("picking_type_code","=","incoming")]`, Motivo "Validar recepción".
- **Inventario – Despacho**: igual, con `"outgoing"`.
- **Ventas**: Documento *Pedido de venta*, Operación *Confirmar*, Motivo
  "Confirmar pedido".
- **Compras**: Documento *Orden de compra*, Operación *Confirmar*.
- **Contabilidad**: Documento *Asiento contable*, Operación *Publicar*, Filtro
  `[("move_type","=","out_invoice")]` (recomendado, ver aviso abajo).

> ⚠️ **Contabilidad**: la publicación de asientos también ocurre en procesos
> automáticos (pagos, conciliación). **Acote siempre** la regla con un dominio
> (p. ej. solo facturas de cliente) para no interferir con esos procesos.

---

## 8. Operación diaria: cómo se ve el PIN

1. El usuario pulsa el botón normal (p. ej. **Validar** en una transferencia).
2. Si una regla aplica, se abre el **diálogo de PIN** (estilo Punto de Venta, con
   teclado numérico) sobre la pantalla y el fondo queda bloqueado:
   - **Si el usuario tiene empleado con PIN**: el diálogo muestra "Autorizando
     como *(su nombre)*" y solo pide **teclear su PIN**. Hay un enlace
     *"Usar otro empleado"* por si debe autorizar un supervisor.
   - **Si el usuario no tiene empleado**: aparece el **buscador de empleado** para
     elegir quién autoriza, y luego se teclea el PIN.
   - Pulsa **Autorizar**.
3. Si el PIN es correcto, la acción continúa automáticamente (la transferencia se
   valida, el pedido se confirma, etc.).
4. Si es incorrecto, se muestra el error y puede reintentar.

> Para cancelar, use **Cancelar** o cierre el diálogo: la acción no se ejecuta.

---

## 9. Trazabilidad: campos, chatter y auditoría

Cada autorización exitosa deja **triple rastro**:

1. **Campos en el documento** (visibles en la pestaña *Autorización por PIN*):
   - *Autorizado por (PIN)* — el empleado.
   - *Fecha de autorización* — fecha y hora.
   - *Autorizado en sesión de* — el usuario que operaba.
2. **Mensaje en el chatter** del documento: *"Autorizado por **X** el …"*.
3. **Log central** en *Ajustes ▸ Autorización por PIN ▸ Auditoría*, que registra
   **todos** los intentos (exitosos y fallidos) con empleado, usuario, fecha,
   motivo, documento y resultado.

---

## 10. Uso en reportes QWeb

Los campos de autorización están **almacenados en el documento**, por lo que se
pueden imprimir en cualquier reporte QWeb. Ejemplo:

```xml
<div t-if="doc.kc_pin_authorized_employee_id">
    <strong>Autorizado por:</strong>
    <span t-field="doc.kc_pin_authorized_employee_id"/>
    el <span t-field="doc.kc_pin_authorization_date"/>
</div>
```

Campos disponibles en el modelo:

| Campo técnico | Contenido |
|---|---|
| `kc_pin_authorized_employee_id` | Empleado que autorizó |
| `kc_pin_authorization_date` | Fecha y hora de la autorización |
| `kc_pin_authorized_user_id` | Usuario que operaba la sesión |

---

## 11. Seguridad: bloqueo por intentos

- El PIN se valida con comparación protegida (no se puede deducir por tiempos).
- Tras **5 intentos fallidos** del mismo empleado en **10 minutos**, se bloquea
  temporalmente su autorización y se avisa en el diálogo. Pasada la ventana,
  vuelve a habilitarse.
- Todos los intentos quedan en la auditoría, lo que permite detectar abusos.

---

## 12. Preguntas frecuentes y solución de problemas

**No aparece ningún empleado en el diálogo.**
Ningún empleado tiene PIN configurado. Configúrelo en la ficha del empleado
(sección 6).

**Pulso Validar y no me pide PIN.**
No hay una regla **activa** que aplique. Revise: documento correcto, operación
correcta (Inventario = *Validar*), filtro que sí incluya este documento, y que la
regla esté activa y en la compañía correcta.

**Me pide PIN en procesos automáticos de contabilidad.**
La regla de `account.move` está demasiado abierta. Acótela con un dominio
(p. ej. `[("move_type","=","out_invoice")]`).

**Quiero suspender temporalmente una regla.**
Desmarque **Activa** en la regla; no hace falta borrarla.

**¿Puede autorizar alguien distinto al usuario logueado?**
Sí. El diálogo permite elegir cualquier empleado con PIN; ideal para que un
supervisor autorice la acción de un operador.

---

## 13. Clasificación para Implementadores

### Modelos

| Modelo | Tipo | Para qué |
|---|---|---|
| `kc.pin.authorization.mixin` | Abstract | Añade campos de rastro y los métodos `_kc_pin_guard` / `kc_action_require_pin` a los modelos que lo heredan. |
| `kc.pin.authorization` | Transient | Hospeda el diálogo y expone `verify_pin` / `get_authorizer_employees` (vía ORM). |
| `kc.pin.authorization.rule` | Model | Reglas configurables (documento, operación, dominio). |
| `kc.pin.authorization.log` | Model | Auditoría de intentos. |

### Catálogo de operaciones (campo `operation`)

`validate`, `confirm`, `post`, `cancel`, `done`. Ampliable por un puente con
`selection_add`.

### Cómo crear un puente nuevo (otro módulo/método)

```python
class MiModelo(models.Model):
    _name = 'mi.modelo'
    _inherit = ['mi.modelo', 'kc.pin.authorization.mixin']

    def mi_metodo(self):
        action = self._kc_pin_guard('confirm', 'mi_metodo')
        if action:
            return action
        return super().mi_metodo()
```

Luego se crea una regla con Documento = `mi.modelo` y Operación = `confirm`.

### Parámetros internos de seguridad

| Parámetro | Valor por defecto | Dónde |
|---|---|---|
| Máx. intentos fallidos | 5 | `MAX_FAILED_ATTEMPTS` en `models/pin_authorization.py` |
| Ventana de bloqueo | 10 min | `ATTEMPT_WINDOW_MINUTES` en `models/pin_authorization.py` |

### Contexto técnico del flujo

- El método objetivo devuelve la acción del diálogo si aplica una regla.
- Tras validar, el diálogo re-ejecuta el método con
  `context = {'kc_pin_authorized': True, 'kc_pin_employee_id': <id>}`.
- El método, al ver `kc_pin_authorized`, ejecuta su lógica real con `super()`.
