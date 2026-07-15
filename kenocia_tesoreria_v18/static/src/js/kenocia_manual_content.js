/** @odoo-module **/

/**
 * Contenido estructurado del Manual de Tesorería KENOCIA.
 * Cada sección se compone de bloques tipados que el template renderiza.
 *
 * Tipos de bloque:
 *  - { type: "p", html }                          párrafo
 *  - { type: "callout", tone, title, text }       nota destacada
 *  - { type: "steps", items: [{ t, d }] }         pasos numerados
 *  - { type: "table", headers, rows }             tabla
 *  - { type: "cards", items: [{ icon, title, text }] }
 *  - { type: "accounting", title, lines: [{ debe, haber, note }] }
 *  - { type: "tags", items: [{ label, tone }] }
 */

export const MANUAL_SECTIONS = [
    {
        id: "roles",
        title: "Roles y permisos",
        icon: "fa-users",
        intro:
            "El módulo define cinco roles bajo la categoría «Tesorería Kenocia». " +
            "Cada usuario ve y opera solo lo que su rol permite.",
        blocks: [
            {
                type: "table",
                headers: ["Rol", "Para qué sirve", "Hereda de"],
                rows: [
                    ["Tesorería CXC", "Cobros, adelantos de clientes y operaciones CXC.", "Usuario interno"],
                    ["Tesorería CXP", "Pagos, adelantos a proveedores, cheques y operaciones CXP.", "Usuario interno"],
                    ["Supervisor de Tesorería", "Todo CXC + CXP, anular cheques, reportes globales y cerrar fondos.", "CXC + CXP"],
                    ["Administrador de Tesorería", "Acceso total: secuencias, configuración y borrado.", "Supervisor"],
                    ["Custodio de Caja Chica", "Solo su(s) fondo(s): anticipos y liquidaciones.", "Usuario interno"],
                ],
            },
            {
                type: "callout",
                tone: "info",
                title: "Herencias automáticas",
                text:
                    "Administrador del sistema ⇒ Administrador de Tesorería. " +
                    "Responsable contable ⇒ Supervisor de Tesorería.",
            },
            {
                type: "cards",
                items: [
                    { icon: "fa-shield", title: "Separación CXC / CXP", text: "Un usuario CXC no puede registrar pagos salientes y un CXP no puede registrar cobros entrantes." },
                    { icon: "fa-lock", title: "Custodio acotado", text: "El custodio solo ve sus propios fondos y los pagos ligados a sus anticipos de caja chica." },
                    { icon: "fa-building", title: "Multicompañía", text: "Todos los registros respetan la(s) compañía(s) del usuario." },
                ],
            },
        ],
    },
    {
        id: "pagos",
        title: "Pagos y cobros",
        icon: "fa-exchange",
        intro:
            "Cobros (CXC) y pagos (CXP) se registran como pagos nativos de Odoo " +
            "con campos extra de Kenocia. La contabilidad la genera el motor estándar.",
        blocks: [
            {
                type: "steps",
                items: [
                    { t: "Elige el tipo de operación", d: "Desde <b>Cobros CXC</b> o <b>Pagos CXP</b> → Cheques / Transferencias / Efectivo." },
                    { t: "Selecciona el Tipo tesorería", d: "Cheque, depósito, débito, crédito, transferencia, transferencia bancaria o efectivo. Esto activa el correlativo Kenocia al confirmar." },
                    { t: "Confirma el pago", d: "Si existe una secuencia activa para (diario, tipo), se consume un correlativo y se guarda en <b>Correlativo tesorería</b>; ese número renombra el asiento." },
                    { t: "Concilia con el banco", d: "Al conciliar el pago contra el extracto, la cuenta <i>outstanding</i> se salda contra la cuenta de banco." },
                ],
            },
            {
                type: "accounting",
                title: "Afectación contable",
                lines: [
                    { debe: "Pagos pendientes a recibir / Banco", haber: "CxC del cliente", note: "Cobro CXC (entrante)" },
                    { debe: "CxP del proveedor", haber: "Pagos pendientes a pagar / Banco", note: "Pago CXP (saliente)" },
                ],
            },
            {
                type: "callout",
                tone: "warning",
                title: "Anulación de cheques",
                text:
                    "Solo para pagos de tipo Cheque y solo Supervisor/Administrador. El correlativo se " +
                    "registra como hueco y nunca se reutiliza; si el cheque estaba publicado, se cancela el asiento.",
            },
            {
                type: "callout",
                tone: "info",
                title: "¿No aparece el correlativo Kenocia?",
                text:
                    "Significa que no hay una secuencia activa para ese (diario, tipo). El pago usa la " +
                    "numeración nativa de Odoo, lo cual es válido.",
            },
        ],
    },
    {
        id: "anticipos",
        title: "Anticipos CXC / CXP",
        icon: "fa-hand-holding-usd",
        intro:
            "Un anticipo registra dinero recibido o pagado antes de la factura, y luego " +
            "se aplica a una o varias facturas vía conciliación nativa.",
        blocks: [
            {
                type: "steps",
                items: [
                    { t: "Crea el anticipo", d: "<b>Adelantos de Clientes</b> (CXC) o <b>Adelantos a Proveedores</b> (CXP). Indica contacto, diario, cuenta de anticipo (se precarga) y monto." },
                    { t: "Confirma", d: "Se asigna la referencia (ADEL-CXC/CXP-aaaa-####) y se crea y publica el pago contra la cuenta de anticipo." },
                    { t: "Aplica a la factura", d: "Desde la factura, botón <b>Aplicar adelantos</b>, o automáticamente al publicar la factura del mismo contacto/moneda." },
                ],
            },
            {
                type: "accounting",
                title: "Al confirmar el anticipo",
                lines: [
                    { debe: "Banco / Outstanding entrante", haber: "Anticipos clientes (PASIVO)", note: "CXC — cliente paga por adelantado" },
                    { debe: "Anticipos proveedores (ACTIVO)", haber: "Banco / Outstanding saliente", note: "CXP — pago anticipado al proveedor" },
                ],
            },
            {
                type: "accounting",
                title: "Al aplicar a la factura (diario general + conciliación)",
                lines: [
                    { debe: "Anticipos clientes (pasivo)", haber: "CxC de la factura", note: "CXC" },
                    { debe: "CxP de la factura", haber: "Anticipos proveedores (activo)", note: "CXP" },
                ],
            },
            {
                type: "callout",
                tone: "info",
                title: "Cancelar o revertir",
                text:
                    "Solo se puede cancelar/volver a borrador un anticipo si no tiene aplicaciones. " +
                    "Las órdenes de venta/compra muestran Total anticipado, Saldo anticipos y Total neto.",
            },
        ],
    },
    {
        id: "caja_chica",
        title: "Caja chica",
        icon: "fa-money",
        intro:
            "Flujo completo: abrir fondo → entregar anticipos → liquidar con factura SAR → " +
            "recargar → cerrar (arqueo).",
        blocks: [
            {
                type: "callout",
                tone: "warning",
                title: "Clave contable",
                text:
                    "La entrega física de efectivo a un empleado NO genera asiento. El impacto contable " +
                    "ocurre en la liquidación (cuando hay factura). Las recargas y el cierre sí generan asientos.",
            },
            {
                type: "steps",
                items: [
                    { t: "Abrir el fondo", d: "Define diario de caja, cuenta puente (tránsito), custodio, vigencia y monto autorizado. Pulsa <b>Abrir fondo</b>." },
                    { t: "Anticipo a empleado", d: "Registra empleado, concepto y monto (≤ disponible). <b>Confirmar entrega</b> → estado Entregado (sin asiento)." },
                    { t: "Liquidar con factura SAR", d: "Cuando el empleado trae la factura, se valida el cumplimiento SAR y se crea el pago desde la caja." },
                    { t: "Recargar", d: "En dos pasos con cuenta puente: Enviar a tránsito (banco→puente) y Confirmar efectivo recibido (puente→caja)." },
                    { t: "Cerrar (arqueo)", d: "Requiere que no haya recargas en tránsito ni anticipos sin liquidar. Calcula la diferencia de arqueo." },
                ],
            },
            {
                type: "accounting",
                title: "Asientos de caja chica",
                lines: [
                    { debe: "—", haber: "—", note: "Entregar anticipo: SIN asiento (entrega física)" },
                    { debe: "CxP del proveedor", haber: "Caja del fondo", note: "Liquidar con factura (+ conciliación)" },
                    { debe: "Cuenta puente", haber: "Banco origen", note: "Recarga paso 1 (banco → tránsito)" },
                    { debe: "Caja del fondo", haber: "Cuenta puente", note: "Recarga paso 2 (tránsito → caja)" },
                    { debe: "Banco de devolución", haber: "Caja del fondo", note: "Cierre (por el saldo según sistema)" },
                ],
            },
        ],
    },
    {
        id: "dispersion",
        title: "Dispersión y pagos masivos",
        icon: "fa-random",
        intro:
            "Tres escenarios sobre un motor común que crea un pago por beneficiario y " +
            "concilia parcialmente por el monto exacto de cada documento.",
        blocks: [
            {
                type: "cards",
                items: [
                    { icon: "fa-user", title: "Esc. 1 — Masivo de un contacto", text: "Un contacto, un pago, contra varias facturas con monto parcial editable." },
                    { icon: "fa-truck", title: "Esc. 2 — A proveedores", text: "Un depósito que dispersa a varios proveedores; agrupa en un lote con correlativo único." },
                    { icon: "fa-users", title: "Esc. 3 — Nómina", text: "Paga el neto de un lote de nómina aprobado, un pago por empleado." },
                ],
            },
            {
                type: "callout",
                tone: "info",
                title: "Modelo de numeración (Opción A)",
                text:
                    "Los pagos individuales usan numeración nativa; el lote recibe un correlativo Kenocia " +
                    "(tipo Transferencia Bancaria) si el diario tiene esa secuencia activa.",
            },
            {
                type: "callout",
                tone: "warning",
                title: "Requisitos",
                text:
                    "Todos los proveedores/empleados deben tener cuenta bancaria registrada. La nómina " +
                    "debe estar aprobada con asiento publicado y líneas por pagar.",
            },
            {
                type: "callout",
                tone: "danger",
                title: "Archivo del banco (TXT) — Fase 2",
                text:
                    "Los generadores TXT por banco aún no están implementados. Al generar el archivo, si el " +
                    "formato no tiene generador, se avisa. Comparta el layout del banco para habilitarlo.",
            },
        ],
    },
    {
        id: "dashboard",
        title: "Dashboard",
        icon: "fa-tachometer",
        intro:
            "Panel de indicadores de tesorería con filtros por compañía, fechas, diarios y fondos.",
        blocks: [
            {
                type: "cards",
                items: [
                    { icon: "fa-university", title: "Bancos y efectivo", text: "Saldos contables reales por diario, con totales y liquidez unificada." },
                    { icon: "fa-money", title: "Caja chica", text: "Por fondo: disponible, autorizado, recargas, % de uso y saldo contable." },
                    { icon: "fa-arrow-down", title: "CXC", text: "Cartera por cobrar con aging (corriente / 1–60 / >60 días) y top 5." },
                    { icon: "fa-arrow-up", title: "CXP", text: "Cuentas por pagar (corriente / ≤7 días / vencido) y top 5." },
                    { icon: "fa-line-chart", title: "Flujo de caja", text: "Proyección a 4 semanas (2 reales + 2 futuras)." },
                    { icon: "fa-bell", title: "Alertas", text: "CXP vencido, CXC crítica y caja chica sin factura SAR." },
                ],
            },
            {
                type: "callout",
                tone: "info",
                title: "Tip",
                text: "Haz clic en las tarjetas KPI para voltearlas y ver una explicación en lenguaje sencillo, y «Ver detalle» para profundizar.",
            },
        ],
    },
    {
        id: "contable",
        title: "Resumen contable",
        icon: "fa-calculator",
        intro:
            "Qué asiento genera cada acción y contra qué cuentas. DEBE = débito, HABER = crédito.",
        blocks: [
            {
                type: "table",
                headers: ["Acción", "DEBE", "HABER"],
                rows: [
                    ["Cobro CXC", "Outstanding entrante / Banco", "CxC del cliente"],
                    ["Pago CXP", "CxP del proveedor", "Outstanding saliente / Banco"],
                    ["Anticipo CXC (confirmar)", "Banco / Outstanding", "Anticipos clientes (pasivo)"],
                    ["Anticipo CXP (confirmar)", "Anticipos proveedores (activo)", "Banco / Outstanding"],
                    ["Aplicar anticipo CXC", "Anticipos clientes (pasivo)", "CxC de la factura"],
                    ["Aplicar anticipo CXP", "CxP de la factura", "Anticipos proveedores (activo)"],
                    ["Caja: entregar anticipo", "— (sin asiento)", "— (sin asiento)"],
                    ["Caja: liquidar con factura", "CxP del proveedor", "Caja del fondo"],
                    ["Caja: recarga (paso 1)", "Cuenta puente", "Banco origen"],
                    ["Caja: recarga (paso 2)", "Caja del fondo", "Cuenta puente"],
                    ["Caja: cierre", "Banco de devolución", "Caja del fondo"],
                    ["Dispersión (por beneficiario)", "CxP del proveedor / empleado", "Outstanding saliente"],
                ],
            },
            {
                type: "callout",
                tone: "success",
                title: "Contabilidad 100% nativa",
                text:
                    "El módulo no inventa asientos salvo en tres casos controlados: aplicación de un anticipo, " +
                    "recarga de caja chica y cierre de caja chica.",
            },
        ],
    },
    {
        id: "faq",
        title: "Preguntas frecuentes",
        icon: "fa-question-circle",
        intro: "Soluciones rápidas a los casos más comunes de operación.",
        blocks: [
            { type: "p", html: "<b>No aparece el correlativo Kenocia en mi pago.</b><br/>No hay una secuencia activa para ese (diario, tipo). El pago usa numeración nativa (es válido). Créala en Configuración → Secuencias Bancarias." },
            { type: "p", html: "<b>«Otro usuario está generando un número…».</b><br/>Es el control anti-duplicados de correlativos. Reintente en unos segundos." },
            { type: "p", html: "<b>El botón «Generar archivo banco» dice que el formato no está configurado.</b><br/>Es la Fase 2: el generador TXT de ese banco aún no está implementado. Comparta el layout del banco." },
            { type: "p", html: "<b>Un proveedor/empleado no entra en la dispersión.</b><br/>Debe tener cuenta bancaria registrada (y, en nómina, líneas contables por pagar)." },
            { type: "p", html: "<b>No puedo cerrar el fondo de caja.</b><br/>No debe haber recargas en tránsito ni anticipos entregados sin liquidar. Liquide o cancele esos movimientos primero." },
            { type: "p", html: "<b>Cambié código Python y no veo el efecto.</b><br/>Los cambios de Python requieren reiniciar el servicio de Odoo." },
        ],
    },
];
