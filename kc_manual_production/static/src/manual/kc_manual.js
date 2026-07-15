/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

const GROUP_PLANNER = "kc_manual_production.kc_production_group_planner";
const GROUP_USER = "kc_manual_production.kc_production_group_user";
const GROUP_BODEGA = "kc_manual_production.kc_production_group_bodega";
const GROUP_MANAGER = "kc_manual_production.kc_production_group_manager";
const GROUP_STOCK_MANAGER = "stock.group_stock_manager";

/**
 * Orden de pestañas del manual. La visibilidad depende del grupo del usuario.
 */
const TAB_ORDER = [
    "flujo",
    "control",
    "planificacion",
    "backlog",
    "produccion",
    "bodega",
    "gerente",
    "config",
];

/**
 * Manual de Usuario — Planta KC.
 * Muestra solo las secciones operables según el rol del usuario conectado.
 */
export class ProductionManual extends Component {
    static template = "kc_manual_production.ProductionManual";
    static props = {
        "*": true,
    };

    setup() {
        this.state = useState({
            ready: false,
            activeTab: "flujo",
            roleLabel: "",
            roleHint: "",
            can: {
                flujo: true,
                control: true,
                planificacion: true,
                backlog: false,
                produccion: false,
                bodega: false,
                gerente: false,
                config: false,
                confirmOp: false,
                validateOp: false,
                cmp: false,
            },
            isPlannerOnly: false,
            isOperator: false,
            isBodegaOnly: false,
            isManager: false,
        });

        onWillStart(async () => {
            await this._resolveAccess();
        });
    }

    async _resolveAccess() {
        const [planner, operator, bodega, manager, stockManager] = await Promise.all([
            user.hasGroup(GROUP_PLANNER),
            user.hasGroup(GROUP_USER),
            user.hasGroup(GROUP_BODEGA),
            user.hasGroup(GROUP_MANAGER),
            user.hasGroup(GROUP_STOCK_MANAGER),
        ]);

        const isManager = Boolean(manager || stockManager);
        const isOperator = Boolean(operator && !isManager);
        // Planificador puro: tiene planner pero no operador, bodega ni admin.
        const isPlannerOnly = Boolean(planner && !operator && !bodega && !isManager);
        const isBodegaOnly = Boolean(bodega && !operator && !isManager);

        const can = {
            flujo: true,
            control: Boolean(planner || operator || bodega || isManager),
            planificacion: Boolean(planner || operator || bodega || isManager),
            // Menú backlog: no bodega sola
            backlog: Boolean(planner || operator || isManager),
            // Generar/ver OP: planificador y producción
            produccion: Boolean(planner || operator || isManager),
            bodega: Boolean(bodega || isManager),
            gerente: isManager,
            config: isManager,
            confirmOp: Boolean(operator || isManager),
            validateOp: Boolean(bodega || isManager),
            cmp: Boolean(bodega || isManager),
        };

        let roleLabel = "Usuario";
        let roleHint = "Se muestran las secciones disponibles según su perfil.";
        if (isManager) {
            roleLabel = "Administrador de Producción";
            roleHint = "Acceso total: planificación, producción, bodega, reportes y configuración.";
        } else if (isOperator) {
            roleLabel = "Operador de Producción";
            roleHint =
                "Puede planificar, generar OP y confirmar. La validación en bodega y el CMP son de otro rol.";
        } else if (isBodegaOnly) {
            roleLabel = "Operador de Bodega";
            roleHint =
                "Puede validar OP (recibir PT) y gestionar consumos. No planifica ni confirma producción.";
        } else if (isPlannerOnly || planner) {
            roleLabel = "Planificador";
            roleHint =
                "Puede planificar, generar OP en borrador e imprimir. No confirma ni valida; eso lo hacen Producción y Bodega.";
        }

        Object.assign(this.state.can, can);
        this.state.isManager = isManager;
        this.state.isOperator = isOperator;
        this.state.isPlannerOnly = isPlannerOnly;
        this.state.isBodegaOnly = isBodegaOnly;
        this.state.roleLabel = roleLabel;
        this.state.roleHint = roleHint;

        const firstTab = TAB_ORDER.find((tab) => can[tab]) || "flujo";
        this.state.activeTab = firstTab;
        this.state.ready = true;
    }

    setActiveTab(tabName) {
        if (!this.state.can[tabName]) {
            return;
        }
        this.state.activeTab = tabName;
    }
}

registry.category("actions").add("kc_production_manual", ProductionManual);
