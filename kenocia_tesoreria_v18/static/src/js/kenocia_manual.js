/** @odoo-module **/

import { Component, useState, onWillStart, markup } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { MANUAL_SECTIONS } from "./kenocia_manual_content";

/** Envuelve los campos con HTML embebido para que t-out los renderice. */
function prepareSection(section) {
    return {
        ...section,
        blocks: section.blocks.map((block) => {
            if (block.type === "p") {
                return { ...block, html: markup(block.html) };
            }
            if (block.type === "steps") {
                return {
                    ...block,
                    items: block.items.map((it) => ({ ...it, d: markup(it.d) })),
                };
            }
            return block;
        }),
    };
}

class KenociaManual extends Component {
    static template = "kenocia_tesoreria_v18.Manual";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.sections = MANUAL_SECTIONS.map(prepareSection);

        this.state = useState({
            loading: true,
            data: null,
            active: "inicio",
            search: "",
        });

        onWillStart(async () => {
            await this._load();
        });
    }

    async _load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "kenocia.treasury.manual",
                "get_manual_data",
                []
            );
        } catch (error) {
            this.notification.add(
                error?.message || "Error cargando el manual",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() {
        await this._load();
    }

    setActive(id) {
        this.state.active = id;
        this.state.search = "";
        const scroller = document.querySelector(".kc-manual-content");
        if (scroller) {
            scroller.scrollTop = 0;
        }
    }

    onSearch(ev) {
        this.state.search = ev.target.value || "";
    }

    get navSections() {
        return [
            { id: "inicio", title: "Inicio", icon: "fa-home" },
            { id: "config", title: "Configuración pendiente", icon: "fa-tasks" },
            { id: "alertas", title: "Alertas", icon: "fa-bell" },
            ...this.sections.map((s) => ({
                id: s.id,
                title: s.title,
                icon: s.icon,
            })),
        ];
    }

    get currentSection() {
        return this.sections.find((s) => s.id === this.state.active) || null;
    }

    get searchHits() {
        const q = (this.state.search || "").trim().toLowerCase();
        if (q.length < 2) {
            return null;
        }
        const hits = [];
        for (const section of this.sections) {
            const haystack = JSON.stringify(section).toLowerCase();
            if (haystack.includes(q)) {
                hits.push(section);
            }
        }
        return hits;
    }

    // ── Configuración ───────────────────────────────────────────────
    get progress() {
        return this.state.data?.progress || { done: 0, total: 0, pct: 0, pending: [] };
    }

    get configGroups() {
        return this.state.data?.config_groups || [];
    }

    get alerts() {
        return this.state.data?.alerts || [];
    }

    get pendingCount() {
        return this.configGroups.reduce(
            (acc, g) =>
                acc + g.items.filter((i) => i.status !== "ok" && i.status !== "info").length,
            0
        );
    }

    statusMeta(status) {
        const map = {
            ok: { icon: "fa-check-circle", cls: "kc-ok", label: "Listo" },
            pending: { icon: "fa-circle-o", cls: "kc-pending", label: "Pendiente" },
            warning: { icon: "fa-exclamation-circle", cls: "kc-warn", label: "Atención" },
            info: { icon: "fa-info-circle", cls: "kc-info", label: "Opcional" },
        };
        return map[status] || map.info;
    }

    groupStatus(group) {
        if (group.items.some((i) => i.status === "pending")) {
            return "pending";
        }
        if (group.items.some((i) => i.status === "warning")) {
            return "warning";
        }
        if (group.items.every((i) => i.status === "ok")) {
            return "ok";
        }
        return "info";
    }

    progressTone() {
        const pct = this.progress.pct;
        if (pct >= 100) {
            return "kc-ring-ok";
        }
        if (pct >= 60) {
            return "kc-ring-warn";
        }
        return "kc-ring-danger";
    }

    alertClass(level) {
        return {
            danger: "kc-alert-danger",
            warning: "kc-alert-warning",
            info: "kc-alert-info",
        }[level] || "kc-alert-info";
    }

    openAction(xmlid) {
        if (xmlid) {
            this.action.doAction(xmlid);
        }
    }
}

registry
    .category("actions")
    .add("kenocia_tesoreria_v18.manual_action", KenociaManual);
