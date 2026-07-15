# KC Autorización por PIN (`kc_pin_authorization`)

Módulo genérico y reutilizable para exigir que un empleado autorice una acción
introduciendo su **PIN** (el mismo campo `pin` de `hr.employee` que usa el POS),
dejando rastro completo: campos en el documento, registro en el chatter y un
log central de auditoría.

## Qué aporta

- **Mixin `kc.pin.authorization.mixin`**: añade a cualquier modelo
  - `kc_pin_authorized_employee_id` — empleado que autorizó.
  - `kc_pin_authorization_date` — fecha y hora de la autorización.
  - `kc_pin_authorized_user_id` — usuario que operaba la sesión.
  - Un mensaje automático en el **chatter** del documento.
  - El helper `kc_action_require_pin(callback_method, reason)`.
- **Servicio `kc.pin.authorization`**: valida el PIN de forma segura
  (comparación de tiempo constante) con **bloqueo temporal** tras varios
  intentos fallidos.
- **Log central `kc.pin.authorization.log`**: auditoría de todos los intentos
  (Ajustes ▸ Técnico ▸ *Autorizaciones por PIN*).
- **Diálogo OWL** con teclado numérico que **bloquea el fondo** (modal nativo).

## Cómo usarlo en otro módulo

### 1. Declarar la dependencia

```python
# __manifest__.py
'depends': ['kc_pin_authorization', ...],
```

### 2. Heredar el mixin en el modelo

El modelo debe heredar también `mail.thread` para el registro en el chatter.

```python
from odoo import _, models


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'kc.pin.authorization.mixin']

    def action_confirm(self):
        # Si aún no se autorizó por PIN, abrir el diálogo (bloquea el fondo).
        if not self.env.context.get('kc_pin_authorized'):
            return self.kc_action_require_pin(
                'action_confirm',
                reason=_('Confirmación de pedido'),
            )
        # Ya autorizado: ejecutar la lógica real.
        return super().action_confirm()
```

Eso es todo. Al pulsar *Confirmar*:

1. Se abre el diálogo de PIN sobre la pantalla actual (fondo bloqueado).
2. El empleado elige su nombre y teclea su PIN.
3. El servicio valida el PIN vía ORM. Si es correcto:
   - Se escriben los campos de rastro en el pedido.
   - Se publica el mensaje en el chatter.
   - Se registra en el log central.
   - Se vuelve a llamar a `action_confirm` con `kc_pin_authorized=True` y se
     ejecuta la confirmación real.

### 3. (Opcional) Mostrar el rastro en la vista

```xml
<group string="Autorización" groups="base.group_no_one">
    <field name="kc_pin_authorized_employee_id"/>
    <field name="kc_pin_authorization_date"/>
</group>
```

## Modo configurable (reglas por documento/operación)

Además del enganche directo, puedes hacer que el PIN sea **configurable desde
Ajustes** sin tocar código cada vez. El flujo es:

1. **El módulo declara un enganche mínimo** en el método objetivo, indicando una
   "operación" lógica:

```python
def button_validate(self):
    action = self._kc_pin_guard('validate', 'button_validate')
    if action:
        return action
    return super().button_validate()
```

2. **El usuario configura las reglas** en *Ajustes ▸ Autorización por PIN ▸
   Reglas* (o el botón "Configurar reglas" en Ajustes). Cada regla define:
   - **Documento** (`model_id`): p. ej. `stock.picking`.
   - **Operación**: la clave que usa el enganche, p. ej. `validate`.
   - **Filtro (dominio)** opcional para acotar a un sub-tipo:
     - Recepción: `[("picking_type_code", "=", "incoming")]`
     - Despacho: `[("picking_type_code", "=", "outgoing")]`
   - **Motivo**, **compañía**, **activa/archivada**.

`_kc_pin_guard` consulta las reglas activas para `(modelo, operación)` y, si el
dominio aplica a los registros, abre el diálogo de PIN. Si no hay regla, el
método continúa sin pedir nada.

> Nota de diseño: Odoo no permite interrumpir una validación con un modal
> bloqueante de forma 100% declarativa (las Acciones Automatizadas corren
> *después* del cambio). Por eso el enganche en el método es necesario, pero es
> una sola línea; **el alcance (qué documento, operación y sub-tipo) es 100%
> configurable**.

## Módulos-puente incluidos

| Módulo | Documento | Método enganchado | Operación |
|---|---|---|---|
| `kc_pin_authorization_stock` | `stock.picking` | `button_validate` | `validate` |
| `kc_pin_authorization_sale` | `sale.order` | `action_confirm` | `confirm` |
| `kc_pin_authorization_purchase` | `purchase.order` | `button_confirm` | `confirm` |
| `kc_pin_authorization_account` | `account.move` | `action_post` | `post` |

Instala el puente del módulo que necesites y crea las reglas correspondientes
en *Ajustes ▸ Autorización por PIN ▸ Reglas*. Acota con el dominio según el caso
(recepción/despacho en inventario, tipo de factura en contabilidad, etc.).

> Aviso para Contabilidad: `account.move.action_post` también se ejecuta en
> flujos automáticos (pagos, conciliación). Acota siempre la regla con un
> dominio específico, p. ej. `[("move_type", "=", "out_invoice")]`, para no
> interferir con la contabilización automática.

## Notas

- El `reason` aparece en el chatter y en el log; úsalo para distinguir la acción
  autorizada (p. ej. "Confirmar pedido", "Anular factura", "Liberar producción").
- Puede aplicarse a varios registros a la vez (el helper usa `self.ids`).
- Los empleados que pueden autorizar son los que tengan un PIN configurado en su
  ficha de empleado.
