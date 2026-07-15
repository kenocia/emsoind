/** @odoo-module **/

import { Component, useState, onWillStart, useExternalListener } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { _t } from "@web/core/l10n/translation";

/**
 * Widget de teclado de PIN para el diálogo de autorización.
 *
 * Se monta sobre el campo `pin` del modelo kc.pin.authorization (en una vista
 * abierta con target='new', cuyo modal ya bloquea el fondo). Lee del registro
 * el destino de la autorización (res_model, res_ids, callback_method, reason),
 * valida el PIN vía ORM (kc.pin.authorization.verify_pin) y, si es correcto,
 * re-ejecuta el método de negocio con el flag kc_pin_authorized en el contexto.
 */
export class PinPadField extends Component {
    static template = "kc_pin_authorization.PinPad";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            mode: "select",
            employees: [],
            employeeId: null,
            currentEmployeeName: "",
            pin: "",
            error: "",
            loading: false,
        });

        // Soporte de teclado físico (números, borrar y confirmar).
        useExternalListener(window, "keydown", this.onKeydown.bind(this));

        onWillStart(async () => {
            const data = await this.orm.call(
                "kc.pin.authorization",
                "kc_pin_dialog_data",
                []
            );
            this.state.employees = data.employees || [];
            const current = data.current_employee;
            if (current && current.has_pin) {
                // Estilo PdV: el usuario autoriza con su propio PIN.
                this.state.mode = "self";
                this.state.employeeId = current.id;
                this.state.currentEmployeeName = current.name;
            } else {
                this.state.mode = "select";
                if (this.state.employees.length === 1) {
                    this.state.employeeId = this.state.employees[0].id;
                }
            }
        });
    }

    useOtherEmployee() {
        // Permite que autorice un empleado distinto (p. ej. un supervisor).
        this.state.mode = "select";
        this.state.employeeId = null;
        this.state.pin = "";
        this.state.error = "";
    }

    get recordData() {
        return this.props.record.data;
    }

    get reason() {
        return this.recordData.reason || "";
    }

    get maskedPin() {
        return "\u2022".repeat(this.state.pin.length);
    }

    onSelectEmployee(ev) {
        this.state.employeeId = parseInt(ev.target.value, 10) || null;
        this.state.error = "";
    }

    press(digit) {
        if (this.state.pin.length < 12) {
            this.state.pin += String(digit);
        }
        this.state.error = "";
    }

    onKeydown(ev) {
        if (this.state.loading) {
            return;
        }
        if (ev.key >= "0" && ev.key <= "9") {
            ev.preventDefault();
            this.press(ev.key);
        } else if (ev.key === "Backspace") {
            ev.preventDefault();
            this.backspace();
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            this.confirm();
        } else if (ev.key === "Escape") {
            ev.preventDefault();
            this.cancel();
        }
    }

    backspace() {
        this.state.pin = this.state.pin.slice(0, -1);
    }

    clearPin() {
        this.state.pin = "";
        this.state.error = "";
    }

    async confirm() {
        if (this.state.loading) {
            return;
        }
        if (!this.state.employeeId) {
            this.state.error = _t("Seleccione un empleado.");
            return;
        }
        if (!this.state.pin) {
            this.state.error = _t("Ingrese el PIN.");
            return;
        }

        this.state.loading = true;
        let res;
        try {
            res = await this.orm.call("kc.pin.authorization", "verify_pin", [
                this.state.employeeId,
                this.state.pin,
                this.recordData.res_model,
                this.recordData.res_ids,
                this.reason,
            ]);
        } catch (error) {
            this.state.loading = false;
            throw error;
        }

        if (!res || !res.success) {
            this.state.loading = false;
            this.state.error = (res && res.error) || _t("PIN incorrecto.");
            this.state.pin = "";
            return;
        }

        // PIN válido: re-ejecutar el método de negocio autorizado. Se delega en
        // el servidor para que la acción resultante quede normalizada
        // (clean_action añade la clave `views` que doAction necesita).
        const result = await this.orm.call(
            "kc.pin.authorization",
            "kc_pin_run_callback",
            [
                this.recordData.res_model,
                this.recordData.res_ids,
                this.recordData.callback_method,
                this.state.employeeId,
            ]
        );

        // Cerrar el modal de PIN y refrescar / encadenar la acción resultante.
        await this.action.doAction({ type: "ir.actions.act_window_close" });
        if (result && typeof result === "object" && result.type) {
            await this.action.doAction(result);
        } else {
            await this.action.doAction({
                type: "ir.actions.client",
                tag: "soft_reload",
            });
        }
    }

    cancel() {
        this.action.doAction({ type: "ir.actions.act_window_close" });
    }
}

export const pinPadField = {
    component: PinPadField,
    supportedTypes: ["char"],
};

registry.category("fields").add("kc_pin_pad", pinPadField);
