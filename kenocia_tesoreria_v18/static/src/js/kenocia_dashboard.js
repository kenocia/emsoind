/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onPatched } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { loadJS } from "@web/core/assets";

class KenociaDashboard extends Component {
    static template = "kenocia_tesoreria_v18.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            activeTab: "exec",
            data: null,
            detailSheet: null,
            flippedCards: {},
            filtersMeta: { companies: [], journals: [], petty_funds: [] },
            filters: {
                company_ids: [],
                journal_ids: [],
                petty_fund_ids: [],
                date_from: "",
                date_to: "",
                period: "month",
            },
        });

        this._charts = {};

        onWillStart(async () => {
            this._initPeriodDates();
            await this._loadData();
            try {
                await loadJS(
                    "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
                );
            } catch {
                console.warn("Chart.js no disponible — gráficas deshabilitadas");
            }
        });

        onMounted(() => this._renderCharts());
        onPatched(() => this._renderCharts());
    }

    _initPeriodDates() {
        const today = new Date();
        const from = new Date(today.getFullYear(), today.getMonth(), 1);
        this.state.filters.date_from = this._formatLocalDate(from);
        this.state.filters.date_to = this._formatLocalDate(today);
    }

    _formatLocalDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    async _loadData() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "kenocia.treasury.dashboard",
                "get_dashboard_data",
                [],
                { filters: this._buildFilters() }
            );
            if (this.state.data?.filters_meta) {
                this.state.filtersMeta = this.state.data.filters_meta;
            }
        } catch (error) {
            console.error("Dashboard tesorería:", error);
            this.notification.add(
                error?.message || "Error cargando datos del dashboard",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    _buildFilters() {
        const f = this.state.filters;
        return {
            company_ids: f.company_ids.length ? f.company_ids : null,
            journal_ids: f.journal_ids.length ? f.journal_ids : null,
            petty_fund_ids: f.petty_fund_ids.length ? f.petty_fund_ids : null,
            date_from: f.date_from || null,
            date_to: f.date_to || null,
        };
    }

    onCompanyChange(ev) {
        const val = ev.target.value;
        this.state.filters.company_ids = val === "all" ? [] : [parseInt(val, 10)];
        this._loadData();
    }

    onJournalChange(ev) {
        const val = ev.target.value;
        this.state.filters.journal_ids = val === "all" ? [] : [parseInt(val, 10)];
        this._loadData();
    }

    onPettyFundChange(ev) {
        const val = ev.target.value;
        this.state.filters.petty_fund_ids = val === "all" ? [] : [parseInt(val, 10)];
        this._loadData();
    }

    onPeriodChange(ev) {
        const val = ev.target.value;
        this.state.filters.period = val;
        const today = new Date();
        let from = new Date();
        if (val === "week") {
            from.setDate(today.getDate() - 7);
        } else if (val === "month") {
            from = new Date(today.getFullYear(), today.getMonth(), 1);
        } else if (val === "q") {
            from = new Date(today.getFullYear(), Math.floor(today.getMonth() / 3) * 3, 1);
        } else if (val === "year") {
            from = new Date(today.getFullYear(), 0, 1);
        }
        this.state.filters.date_from = this._formatLocalDate(from);
        this.state.filters.date_to = this._formatLocalDate(today);
        this._loadData();
    }

    onDateChange(field, ev) {
        this.state.filters[field] = ev.target.value;
        this._loadData();
    }

    resetFilters() {
        this.state.filters.company_ids = [];
        this.state.filters.journal_ids = [];
        this.state.filters.petty_fund_ids = [];
        this.state.filters.period = "month";
        this._initPeriodDates();
        this._loadData();
    }

    get hasActiveFilters() {
        const f = this.state.filters;
        return Boolean(
            f.company_ids.length ||
            f.journal_ids.length ||
            f.petty_fund_ids.length
        );
    }

    setTab(tab) {
        this.state.activeTab = tab;
    }

    toggleFlip(key) {
        this.state.flippedCards[key] = !this.state.flippedCards[key];
    }

    isFlipped(key) {
        return !!this.state.flippedCards[key];
    }

    getKpiExplanation(key) {
        const d = this.state.data;
        if (!d) {
            return { title: "Sin información", text: "", tone: "info" };
        }
        const explanations = {
            saldo_bancos: () => {
                const isCash = this.journalFilterType() === "cash";
                const val = this.primaryLiquidityValue();
                if (val < 0) {
                    return {
                        title: "¿Qué significa?",
                        text: isCash
                            ? "Tu efectivo en caja está en negativo, lo que suele indicar un error de registro. Revisa los movimientos de caja."
                            : "Tus cuentas bancarias están en sobregiro. Puede ser una línea de crédito o algo que requiere atención. Verifica con tu banco.",
                        tone: "danger",
                    };
                }
                return {
                    title: "¿Qué significa?",
                    text: isCash
                        ? "Es el efectivo disponible en tus diarios de caja en este momento."
                        : "Es el dinero disponible en tus cuentas bancarias ahora, sin contar caja chica ni cuentas por cobrar.",
                    tone: "success",
                };
            },
            cajas_chicas: () => ({
                title: "¿Qué significa?",
                text: "Es el efectivo físico disponible en tus fondos de caja chica para gastos menores. No incluye anticipos entregados sin liquidar.",
                tone: "success",
            }),
            cxc: () => ({
                title: "¿Qué significa?",
                text: "Es el dinero que tus clientes te deben por facturas ya emitidas. Mientras más alto y más viejo, mayor riesgo de no cobrarlo.",
                tone: d.cxc.count_critical > 0 ? "warning" : "success",
            }),
            cxp: () => ({
                title: "¿Qué significa?",
                text: d.cxp.overdue > 0
                    ? "Tienes facturas de proveedores vencidas sin pagar. Esto puede afectar tu relación comercial y generar recargos."
                    : "Es el dinero que debes a tus proveedores por facturas recibidas. Mantenerlo al día protege tu relación comercial.",
                tone: d.cxp.overdue > 0 ? "danger" : "success",
            }),
            liquidez_neta: () => {
                const net = this.netLiquidity();
                return {
                    title: "¿Qué significa?",
                    text: net < 0
                        ? "Tus deudas a proveedores (CXP) superan tu efectivo disponible (bancos + caja chica). Vigila tu liquidez de corto plazo."
                        : "Es lo que te queda tras restar tus deudas a proveedores (CXP) de tu efectivo disponible (bancos + caja chica).",
                    tone: net < 0 ? "danger" : "success",
                };
            },
            ratio_cxc_cxp: () => {
                if (!d.cxp.total) {
                    return {
                        title: "¿Qué significa?",
                        text: "No tienes cuentas por pagar pendientes en este momento.",
                        tone: "info",
                    };
                }
                const r = d.cxc.total / d.cxp.total;
                if (r >= 1.5) {
                    return {
                        title: "¿Qué significa?",
                        text: `Por cada L1 que debes, tienes L${r.toFixed(2)} por cobrar. Arriba de 1.5x es saludable: cubres tus deudas con lo que te deben.`,
                        tone: "success",
                    };
                }
                if (r >= 1.0) {
                    return {
                        title: "¿Qué significa?",
                        text: `Por cada L1 que debes, tienes L${r.toFixed(2)} por cobrar. Es adecuado, pero con poco margen — vigila tu cobranza.`,
                        tone: "warning",
                    };
                }
                return {
                    title: "¿Qué significa?",
                    text: `Por cada L1 que debes, solo tienes L${r.toFixed(2)} por cobrar. Tus deudas superan lo que te deben — riesgo de iliquidez.`,
                    tone: "danger",
                };
            },
            criticos: () => ({
                title: "¿Qué significa?",
                text: d.cxc.count_critical > 0
                    ? `Tienes ${d.cxc.count_critical} factura(s) con más de 60 días de atraso. A mayor antigüedad, menor probabilidad de cobro — gestiona la cobranza directa.`
                    : "No tienes facturas con más de 60 días de atraso. Tu cartera está sana en antigüedad.",
                tone: d.cxc.count_critical > 0 ? "danger" : "success",
            }),
        };
        const build = explanations[key];
        return build ? build() : { title: "Sin información", text: "", tone: "info" };
    }

    _selectedFilterValue(ids) {
        return ids.length === 1 ? String(ids[0]) : "all";
    }

    async refresh() {
        await this._loadData();
    }

    openDetailSheet(key) {
        const d = this.state.data;
        if (!d) {
            return;
        }
        const sheets = {
            banks: {
                title: `Cuentas de liquidez — ${this.liquidityBars().length} activas`,
                action: null,
                rows: this.liquidityBars()
                    .map((j) => ({
                        label: `${j.name} (${j.kind === "cash" ? "efectivo" : "banco"})`,
                        value: this.fmt(j.balance),
                        cls: j.balance >= 0 ? "ok" : "bad",
                    }))
                    .concat([{
                        label: "Total",
                        value: this.fmt(this.liquidityBarsTotal()),
                        cls: "bold",
                    }]),
            },
            petty: {
                title: `Cajas chicas — ${d.petty_cash.open_count} fondos abiertos`,
                action: "kenocia_tesoreria_v18.action_kenocia_petty_cash",
                rows: d.petty_cash.funds
                    .map((f) => ({
                        label: f.name,
                        value: `${this.fmt(f.accounting_balance)} contable`,
                        sub: `Operativo: ${this.fmt(f.available)} | ${f.pct}% disp.`,
                        cls: f.pct > 50 ? "ok" : f.pct > 20 ? "warn" : "bad",
                    }))
                    .concat([
                        {
                            label: "Total contable (físico real)",
                            value: this.fmt(d.petty_cash.total_available),
                            cls: "bold ok",
                        },
                        {
                            label: "Total operativo (control fondo)",
                            value: this.fmt(d.petty_cash.total_operational),
                            cls: "bold",
                        },
                    ]),
            },
            cxc: {
                title: "Por cobrar CXC",
                action: "kenocia_tesoreria_v18.action_kenocia_payment_cxc",
                rows: [
                    {
                        label: `Al día (<30d) — ${d.cxc.count_current} fact.`,
                        value: this.fmt(d.cxc.current),
                        cls: "ok",
                    },
                    {
                        label: `30–60 días — ${d.cxc.count_warning} fact.`,
                        value: this.fmt(d.cxc.warning),
                        cls: "warn",
                    },
                    {
                        label: `Vencidas >60d — ${d.cxc.count_critical} fact.`,
                        value: this.fmt(d.cxc.critical),
                        cls: "bad",
                    },
                    {
                        label: `Total — ${d.cxc.count} facturas`,
                        value: this.fmt(d.cxc.total),
                        cls: "bold",
                    },
                ],
            },
            cxp: {
                title: "Por pagar CXP",
                action: "kenocia_tesoreria_v18.action_kenocia_payment_cxp",
                rows: [
                    {
                        label: `Al día — ${d.cxp.count_current} fact.`,
                        value: this.fmt(d.cxp.current),
                        cls: "ok",
                    },
                    {
                        label: `Vence esta semana — ${d.cxp.count_week} fact.`,
                        value: this.fmt(d.cxp.due_week),
                        cls: "warn",
                    },
                    {
                        label: `Vencidas — ${d.cxp.count_overdue} proveedores`,
                        value: this.fmt(d.cxp.overdue),
                        cls: "bad",
                    },
                    {
                        label: `Total — ${d.cxp.count} facturas`,
                        value: this.fmt(d.cxp.total),
                        cls: "bold",
                    },
                ],
            },
            neta: {
                title: "Posición de liquidez neta",
                action: null,
                rows: [
                    {
                        label: "Saldo bancos",
                        value: this.fmt(d.banks.total),
                        cls: "info",
                    },
                    {
                        label: "Cajas chicas (contable)",
                        value: this.fmt(d.petty_cash.total_available),
                        cls: "ok",
                    },
                    {
                        label: "Cajas chicas (operativo)",
                        value: this.fmt(d.petty_cash.total_operational),
                        cls: "info",
                    },
                    {
                        label: "Total activos líquidos",
                        value: this.fmt(d.banks.total + d.petty_cash.total_available),
                        cls: "bold",
                    },
                    {
                        label: "Menos: CXP total",
                        value: `— ${this.fmt(d.cxp.total)}`,
                        cls: "bad",
                    },
                    {
                        label: "Liquidez neta",
                        value: this.fmt(this.netLiquidity()),
                        cls: "bold purple",
                    },
                ],
            },
            criticos: {
                title: "Facturas CXC críticas >60 días",
                action: "kenocia_tesoreria_v18.action_kenocia_payment_cxc",
                rows: (d.cxc.top || [])
                    .filter((r) => r.days > 60)
                    .map((r) => ({
                        label: r.partner,
                        value: `${this.fmt(r.amount)} — ${r.days}d`,
                        cls: "bad",
                    })),
            },
        };
        this.state.detailSheet = sheets[key] || { title: key, rows: [], action: null };
    }

    closeDetailSheet() {
        this.state.detailSheet = null;
    }

    openDetailAction() {
        const actionXmlId = this.state.detailSheet?.action;
        if (actionXmlId) {
            this.action.doAction(actionXmlId);
        }
    }

    openCXC() {
        this.action.doAction("kenocia_tesoreria_v18.action_kenocia_payment_cxc");
    }

    openCXP() {
        this.action.doAction("kenocia_tesoreria_v18.action_kenocia_payment_cxp");
    }

    openPetty() {
        this.action.doAction("kenocia_tesoreria_v18.action_kenocia_petty_cash");
    }

    journalFilterType() {
        return this.state.data?.filter_context?.journal_type || "all";
    }

    cashTotal() {
        return this.state.data?.cash_total || 0;
    }

    cashCount() {
        return this.state.data?.cash_journals?.length || 0;
    }

    pettyCashKpiValue() {
        const d = this.state.data;
        if (!d) {
            return 0;
        }
        if (this.journalFilterType() === "cash") {
            return this.cashTotal() || d.petty_cash.total_available || 0;
        }
        return d.petty_cash.total_available || 0;
    }

    liquidityBars() {
        return this.state.data?.liquidity_journals?.journals || [];
    }

    liquidityBarsTotal() {
        return this.state.data?.liquidity_journals?.total || 0;
    }

    liquidityBarColor(kind) {
        return kind === "cash" ? "#3B6D11" : "#185FA5";
    }

    primaryLiquidityLabel() {
        const type = this.journalFilterType();
        if (type === "cash") {
            return "Efectivo en caja";
        }
        return "Saldo bancos";
    }

    primaryLiquidityValue() {
        const type = this.journalFilterType();
        if (type === "cash") {
            return this.cashTotal();
        }
        return this.state.data?.banks?.total || 0;
    }

    primaryLiquiditySub() {
        const type = this.journalFilterType();
        if (type === "cash") {
            return `${this.cashCount()} diario(s)`;
        }
        return `${this.state.data?.banks?.count || 0} cuentas`;
    }

    fmt(v) {
        if (v == null || Number.isNaN(v)) {
            return "—";
        }
        return "L " + Math.round(v).toLocaleString("es-HN");
    }

    pct(part, whole) {
        return whole ? Math.min(100, Math.round((part / whole) * 100)) : 0;
    }

    barColor(pct) {
        return pct > 50 ? "#3B6D11" : pct > 20 ? "#BA7517" : "#E24B4A";
    }

    ratio() {
        const d = this.state.data;
        if (!d || !d.cxp.total) {
            return "—";
        }
        return (d.cxc.total / d.cxp.total).toFixed(2) + "x";
    }

    netLiquidity() {
        const d = this.state.data;
        if (!d) {
            return 0;
        }
        const type = this.journalFilterType();
        if (type === "cash") {
            return this.cashTotal() - d.cxp.total;
        }
        if (type === "bank") {
            return d.banks.total - d.cxp.total;
        }
        return d.banks.total + d.petty_cash.total_available - d.cxp.total;
    }

    flowTotals() {
        const d = this.state.data;
        if (!d) {
            return { inflow: 0, outflow: 0, net: 0 };
        }
        const inflow = d.cash_flow.reduce((s, w) => s + w.inflow, 0);
        const outflow = d.cash_flow.reduce((s, w) => s + w.outflow, 0);
        return { inflow, outflow, net: inflow - outflow };
    }

    cxcBadgeClass(days) {
        if (days > 60) {
            return "kenocia-badge-danger";
        }
        if (days > 30) {
            return "kenocia-badge-warning";
        }
        return "kenocia-badge-info";
    }

    cxpBadgeLabel(days) {
        return days >= 0 ? "Hoy" : `${Math.abs(days)}d`;
    }

    alertClass(level) {
        if (level === "danger") {
            return "kenocia-alert-danger";
        }
        if (level === "warning") {
            return "kenocia-alert-warning";
        }
        return "kenocia-alert-ok";
    }

    _renderCharts() {
        if (!this.state.data || !window.Chart) {
            return;
        }
        const d = this.state.data;
        const tab = this.state.activeTab;

        if (tab === "exec" || tab === "flow") {
            this._renderFlowChart("kenocia-c-flow", d.cash_flow, 160);
        }
        if (tab === "flow") {
            this._renderFlowChart("kenocia-c-flow2", d.cash_flow, 220);
        }
        if (tab === "ops") {
            this._renderAgingChart(d.cxc);
        }
    }

    _renderFlowChart(id, data, height) {
        const canvas = document.getElementById(id);
        if (!canvas) {
            return;
        }
        canvas.parentElement.style.height = `${height}px`;
        if (this._charts[id]) {
            this._charts[id].destroy();
        }
        const inColors = data.map((w) => (w.is_future ? "#639922" : "#97C459"));
        const outColors = data.map((w) => (w.is_future ? "#D85A30" : "#F0997B"));

        this._charts[id] = new Chart(canvas, {
            type: "bar",
            data: {
                labels: data.map((w) => w.label),
                datasets: [
                    {
                        label: "Entradas",
                        data: data.map((w) => w.inflow),
                        backgroundColor: inColors,
                        borderRadius: 3,
                    },
                    {
                        label: "Salidas",
                        data: data.map((w) => -w.outflow),
                        backgroundColor: outColors,
                        borderRadius: 3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { font: { size: 10 }, autoSkip: false },
                    },
                    y: {
                        ticks: {
                            font: { size: 9 },
                            callback: (v) =>
                                "L " + (Math.abs(v) / 1000).toFixed(0) + "k",
                        },
                        grid: { color: "rgba(128,128,128,0.1)" },
                    },
                },
            },
        });
    }

    _renderAgingChart(cxc) {
        const canvas = document.getElementById("kenocia-c-aging");
        if (!canvas) {
            return;
        }
        if (this._charts.aging) {
            this._charts.aging.destroy();
        }
        this._charts.aging = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: ["Al día", "30–60d", ">60d"],
                datasets: [{
                    data: [
                        Math.round(cxc.current),
                        Math.round(cxc.warning),
                        Math.round(cxc.critical),
                    ],
                    backgroundColor: ["#639922", "#BA7517", "#E24B4A"],
                    borderWidth: 0,
                    hoverOffset: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (c) =>
                                `${c.label}: L ${Math.round(c.parsed).toLocaleString("es-HN")}`,
                        },
                    },
                },
            },
        });
    }
}

registry.category("actions").add(
    "kenocia_tesoreria_v18.dashboard_action",
    KenociaDashboard
);
