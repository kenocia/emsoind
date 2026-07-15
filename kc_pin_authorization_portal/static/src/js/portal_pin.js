/* Validación en vivo y UX de la página "Cambiar mi PIN" del portal.
   JS vanilla, sin dependencias: degrada con gracia (sin JS, el formulario
   funciona igual y la validación la hace el servidor). */
(function () {
    "use strict";

    var MIN_LEN = 4;

    function onlyDigits(value) {
        return (value || "").replace(/\D/g, "");
    }

    function setHint(form, rule, ok) {
        var li = form.querySelector('[data-rule="' + rule + '"]');
        if (li) {
            li.classList.toggle("kc_ok", !!ok);
        }
    }

    function init() {
        var form = document.getElementById("kc_pin_form");
        if (!form) {
            return;
        }
        var newPin = form.querySelector('input[name="new_pin"]');
        var confirmPin = form.querySelector('input[name="confirm_pin"]');
        var submit = form.querySelector(".kc_pin_submit");

        function validate() {
            var v1 = newPin.value;
            var v2 = confirmPin.value;
            var isNum = v1.length > 0 && /^\d+$/.test(v1);
            var isLen = v1.length >= MIN_LEN;
            var isMatch = v1.length > 0 && v1 === v2;

            setHint(form, "num", isNum);
            setHint(form, "len", isLen);
            setHint(form, "match", isMatch);

            var valid = isNum && isLen && isMatch;
            if (submit) {
                submit.disabled = !valid;
            }
            return valid;
        }

        // Fuerza solo dígitos mientras se escribe.
        [newPin, confirmPin].forEach(function (input) {
            if (!input) {
                return;
            }
            input.addEventListener("input", function () {
                var clean = onlyDigits(input.value);
                if (clean !== input.value) {
                    input.value = clean;
                }
                validate();
            });
        });

        // Botones de mostrar/ocultar PIN.
        form.querySelectorAll(".kc_pin_toggle").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var targetName = btn.getAttribute("data-target");
                var target = form.querySelector('input[name="' + targetName + '"]');
                if (!target) {
                    return;
                }
                var icon = btn.querySelector("i");
                if (target.type === "password") {
                    target.type = "text";
                    if (icon) {
                        icon.classList.remove("fa-eye");
                        icon.classList.add("fa-eye-slash");
                    }
                } else {
                    target.type = "password";
                    if (icon) {
                        icon.classList.remove("fa-eye-slash");
                        icon.classList.add("fa-eye");
                    }
                }
            });
        });

        validate();
    }

    if (document.readyState !== "loading") {
        init();
    } else {
        document.addEventListener("DOMContentLoaded", init);
    }
})();
