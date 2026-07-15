/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { SaleOrderLineProductField } from "@sale/js/sale_product_field";

/**
 * Replica el comportamiento del configurador de variantes de Odoo: al fijar un
 * producto con atributos técnicos en la línea de venta, abre automáticamente el
 * wizard de especificaciones técnicas.
 */
patch(SaleOrderLineProductField.prototype, {
    setup() {
        super.setup();
        // Servicios CRUDOS (no envueltos por useService): al guardar la orden, la
        // celda de producto se re-renderiza y este componente se destruye. Los
        // servicios de useService descartan sus promesas cuando el componente
        // muere, por lo que orm.call quedaría colgado y doAction nunca correría.
        this.kcActionService = this.env.services.action;
        this.kcOrmService = this.env.services.orm;
    },

    async _onProductUpdate() {
        await super._onProductUpdate(...arguments);
        this._kcOpenTechnicalSpecsWizard().catch((error) => {
            this.env.services.notification.add(
                error?.message?.data?.message || error?.message || String(error),
                { type: "danger", title: "Especificaciones técnicas" }
            );
        });
    },

    async _kcOpenTechnicalSpecsWizard() {
        const record = this.props.record;
        const model = record.model;
        const productId = record.data.product_id && record.data.product_id[0];
        if (!productId) {
            return;
        }
        if (record.data.show_technical_section === false) {
            return;
        }

        // Id de la línea si ya existía (cambio de producto en línea guardada).
        const existingLineId = record.resId;

        // El wizard trabaja del lado servidor: persistir la orden para que la
        // línea tenga id, sin perder otras ediciones.
        const orderLine = model.root.data.order_line;
        if (orderLine) {
            await orderLine.leaveEditMode();
        }
        const saved = await model.root.save();
        if (!saved) {
            return;
        }

        // Tras guardar/recargar, el `record` capturado puede quedar obsoleto:
        // tomar el id de la línea desde la lista viva de la orden.
        let lineId = existingLineId;
        if (!lineId) {
            const liveRecords = model.root.data.order_line.records;
            const candidates = liveRecords.filter(
                (r) =>
                    r.data.product_id &&
                    r.data.product_id[0] === productId &&
                    !r.data.technical_key
            );
            lineId = candidates.length
                ? candidates[candidates.length - 1].resId
                : undefined;
        }
        if (!lineId) {
            return;
        }

        const action = await this.kcOrmService.call(
            "sale.order.line",
            "action_kc_auto_open_specs_wizard",
            [lineId],
        );
        if (!action) {
            return;
        }

        await this.kcActionService.doAction(action, {
            onClose: () => model.root.load(),
        });
    },
});
