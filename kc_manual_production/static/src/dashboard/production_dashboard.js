/** @odoo-module **/

import { Component, useState, useRef, onWillStart, onWillUnmount, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";

const MODEL = "kc.production.dashboard";

/**
 * Resumen de Producción: Operación / Planificación / Cumplimiento.
 */
export class ProductionDashboard extends Component {
    static template = "kc_manual_production.ProductionDashboard";
    static props = {
        "*": true,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.opCanvasRef = useRef("opChartCanvas");
        this.compCanvasRef = useRef("compChartCanvas");
        this.opChart = null;
        this.compChart = null;

        this.state = useState({
            loading: true,
            activeTab: "operation",
            rangeType: "today",
            dateFrom: null,
            dateTo: null,
            productionLineId: false,
            workCenterId: false,
            productionLines: [],
            workCenters: [],
            data: null,
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            const [range, lines] = await Promise.all([
                this.orm.call(MODEL, "get_date_range", ["today"]),
                this.orm.call(MODEL, "get_production_lines", []),
            ]);
            this.state.dateFrom = range.date_from;
            this.state.dateTo = range.date_to;
            this.state.productionLines = lines;
            if (lines.length === 1) {
                this.state.productionLineId = lines[0].id;
            }
            await this._loadWorkCenters();
            await this._fetchData();
        });

        useEffect(
            () => {
                this._renderCharts();
            },
            () => [this.state.data, this.state.activeTab]
        );

        onWillUnmount(() => {
            this._destroyCharts();
        });
    }

    _destroyCharts() {
        if (this.opChart) {
            this.opChart.destroy();
            this.opChart = null;
        }
        if (this.compChart) {
            this.compChart.destroy();
            this.compChart = null;
        }
    }

    async _loadWorkCenters() {
        this.state.workCenters = await this.orm.call(MODEL, "get_work_centers", [
            this.state.productionLineId || false,
        ]);
        if (
            this.state.workCenterId &&
            !this.state.workCenters.some((c) => c.id === this.state.workCenterId)
        ) {
            this.state.workCenterId = false;
        }
    }

    async _fetchData() {
        this.state.loading = true;
        this.state.data = await this.orm.call(MODEL, "get_dashboard_data", [
            this.state.dateFrom,
            this.state.dateTo,
            this.state.productionLineId || false,
            this.state.workCenterId || false,
        ]);
        this.state.loading = false;
    }

    setTab(tab) {
        this.state.activeTab = tab;
    }

    async onFilterChange(rangeType) {
        this.state.rangeType = rangeType;
        if (rangeType !== "custom") {
            const range = await this.orm.call(MODEL, "get_date_range", [rangeType]);
            this.state.dateFrom = range.date_from;
            this.state.dateTo = range.date_to;
            await this._fetchData();
        }
    }

    async onCustomDateChange(field, ev) {
        const value = ev.target.value;
        if (!value) {
            return;
        }
        if (field === "from") {
            this.state.dateFrom = value;
        } else {
            this.state.dateTo = value;
        }
        if (this.state.dateFrom && this.state.dateTo) {
            await this._fetchData();
        }
    }

    async onProductionLineChange(ev) {
        const value = ev.target.value;
        this.state.productionLineId = value ? parseInt(value, 10) : false;
        this.state.workCenterId = false;
        await this._loadWorkCenters();
        await this._fetchData();
    }

    async onWorkCenterChange(ev) {
        const value = ev.target.value;
        this.state.workCenterId = value ? parseInt(value, 10) : false;
        await this._fetchData();
    }

    async openKpi(kpiType) {
        const action = await this.orm.call(MODEL, "action_open_kpi", [
            kpiType,
            this.state.dateFrom,
            this.state.dateTo,
            this.state.productionLineId || false,
            this.state.workCenterId || false,
        ]);
        this.action.doAction(action);
    }

    async openPlan(planId) {
        const action = await this.orm.call(MODEL, "action_open_plan", [planId]);
        this.action.doAction(action);
    }

    async onAlertAction(alert) {
        if (alert.action === "open_cmp" && alert.res_id) {
            const action = await this.orm.call(MODEL, "action_open_cmp", [alert.res_id]);
            this.action.doAction(action);
        } else if (alert.action === "create_cmp" && alert.line_id) {
            const action = await this.orm.call(MODEL, "action_create_daily_cmp", [
                alert.line_id,
                alert.consumption_date || this.state.dateFrom,
            ]);
            this.action.doAction(action);
            await this._fetchData();
        }
    }

    async onLineAction(row) {
        if (row.action_type === "view_cmp" || row.action_type === "open_cmp") {
            const action = await this.orm.call(MODEL, "action_open_cmp", [row.action_res_id]);
            this.action.doAction(action);
        } else if (row.action_type === "create_cmp") {
            const action = await this.orm.call(MODEL, "action_create_daily_cmp", [
                row.line_id,
                row.action_date,
            ]);
            this.action.doAction(action);
            await this._fetchData();
        }
    }

    async onCalendarCell(lineId, cell) {
        if (cell.status === "closed" || cell.status === "open") {
            if (cell.cmp_id) {
                const action = await this.orm.call(MODEL, "action_open_cmp", [cell.cmp_id]);
                this.action.doAction(action);
            }
        } else if (cell.status === "orphan") {
            const action = await this.orm.call(MODEL, "action_create_daily_cmp", [
                lineId,
                cell.date,
            ]);
            this.action.doAction(action);
            await this._fetchData();
        }
    }

    get rangeLabel() {
        switch (this.state.rangeType) {
            case "today":
                return "hoy";
            case "week":
                return "semana";
            case "month":
                return "mes";
            default:
                return "rango";
        }
    }

    get operation() {
        return (this.state.data && this.state.data.operation) || null;
    }

    get planning() {
        return (this.state.data && this.state.data.planning) || null;
    }

    get compliance() {
        return (this.state.data && this.state.data.compliance) || null;
    }

    kpiStatusClass(status) {
        return {
            green: "kc_kpi_green",
            amber: "kc_kpi_amber",
            red: "kc_kpi_red",
        }[status] || "kc_kpi_teal";
    }

    statusBadgeClass(code) {
        return {
            ok: "text-bg-success",
            open: "text-bg-warning",
            blocked: "text-bg-danger",
            orphan: "text-bg-danger",
            idle: "text-bg-secondary",
        }[code] || "text-bg-secondary";
    }

    calendarCellClass(status) {
        return {
            closed: "kc_cal_closed",
            open: "kc_cal_open",
            orphan: "kc_cal_orphan",
            idle: "kc_cal_idle",
        }[status] || "kc_cal_idle";
    }

    calendarCellIcon(status) {
        return {
            closed: "✓",
            open: "…",
            orphan: "!",
            idle: "—",
        }[status] || "—";
    }

    alertClass(severity) {
        return severity === "critical" ? "kc_alert_critical" : "kc_alert_warning";
    }

    formatNumber(value) {
        return (value || 0).toLocaleString(undefined, {
            maximumFractionDigits: 0,
        });
    }

    formatDecimal(value) {
        return (value || 0).toLocaleString(undefined, {
            maximumFractionDigits: 1,
        });
    }

    get hasOpChartData() {
        const cd = this.operation && this.operation.chart_data;
        if (!cd || !cd.labels.length) {
            return false;
        }
        const totalUnits = cd.units_produced.reduce((a, b) => a + b, 0);
        const totalClosed = cd.lines_closed.reduce((a, b) => a + b, 0);
        return totalUnits > 0 || totalClosed > 0;
    }

    get hasCompChartData() {
        const cd = this.compliance && this.compliance.chart_data;
        if (!cd || !cd.labels.length) {
            return false;
        }
        return cd.planned.some((v) => v > 0) || cd.produced.some((v) => v > 0);
    }

    _renderCharts() {
        this._destroyCharts();
        if (this.state.activeTab === "operation") {
            this._renderOpChart();
        } else if (this.state.activeTab === "compliance") {
            this._renderCompChart();
        }
    }

    _renderOpChart() {
        if (!this.opCanvasRef.el || !this.operation || !this.hasOpChartData) {
            return;
        }
        const cd = this.operation.chart_data;
        const maxLines = cd.lines_total || 1;
        this.opChart = new Chart(this.opCanvasRef.el, {
            type: "bar",
            data: {
                labels: cd.labels,
                datasets: [
                    {
                        type: "bar",
                        label: "Unidades PT producidas",
                        data: cd.units_produced,
                        backgroundColor: "#1ABC9C",
                        borderColor: "#16A085",
                        borderWidth: 1,
                        yAxisID: "y",
                        order: 2,
                    },
                    {
                        type: "bar",
                        label: "Líneas con cierre validado",
                        data: cd.lines_closed,
                        backgroundColor: "#28A745",
                        borderColor: "#1E7E34",
                        borderWidth: 1,
                        yAxisID: "y1",
                        order: 3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: { legend: { position: "top" } },
                scales: {
                    y: {
                        type: "linear",
                        position: "left",
                        beginAtZero: true,
                        title: { display: true, text: "Unidades PT" },
                    },
                    y1: {
                        type: "linear",
                        position: "right",
                        beginAtZero: true,
                        max: maxLines,
                        ticks: { stepSize: 1 },
                        title: { display: true, text: "Líneas cerradas" },
                        grid: { drawOnChartArea: false },
                    },
                },
            },
        });
    }

    _renderCompChart() {
        if (!this.compCanvasRef.el || !this.compliance || !this.hasCompChartData) {
            return;
        }
        const cd = this.compliance.chart_data;
        this.compChart = new Chart(this.compCanvasRef.el, {
            type: "bar",
            data: {
                labels: cd.labels,
                datasets: [
                    {
                        label: "Planificado",
                        data: cd.planned,
                        backgroundColor: "#5DADE2",
                        borderColor: "#3498DB",
                        borderWidth: 1,
                    },
                    {
                        label: "Producido",
                        data: cd.produced,
                        backgroundColor: "#1ABC9C",
                        borderColor: "#16A085",
                        borderWidth: 1,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: { legend: { position: "top" } },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: { display: true, text: "Cantidad" },
                    },
                },
            },
        });
    }
}

registry.category("actions").add("kc_production_dashboard", ProductionDashboard);
