/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { SIZES } from "@web/core/ui/ui_service";
import { FormController } from "@web/views/form/form_controller";
import { FormRenderer } from "@web/views/form/form_renderer";

/**
 * Where the chatter sits on a form, chosen by each user in My Preferences.
 *
 * Odoo puts the chatter (or an attachment preview) beside the sheet once the
 * screen is extra wide (1400 pixels), and the form template decides that from the
 * screen size it reads off the ui service.
 *
 * "Below the form": the form is handed a screen size capped just under that, so a
 * wide screen is laid out the way Odoo lays out a normal one: chatter below, no
 * preview beside it, and the wide-screen class dropped.
 *
 * "Beside the form": from a large screen (992 pixels) up, the form is handed the
 * extra wide size, so the chatter sits beside it where Odoo would put it underneath.
 * Phones and small tablets keep Odoo's own layout: there is no room beside the form
 * there. The attachment preview stays where Odoo shows it: beside the form on an
 * extra wide screen only.
 */
const position = () => session.om_chatter_position || "auto";
const chatterBelow = () => position() === "bottom";
const chatterBeside = (size) => position() === "side" && size >= SIZES.LG;

// The stacking on a wide screen is done in CSS, under this class (see
// chatter_position.scss).
document.documentElement.classList.toggle("o_om_chatter_below", chatterBelow());

patch(FormRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.uiService && (chatterBelow() || position() === "side")) {
            const ui = this.uiService;
            this.omRealUi = ui;
            this.uiService = new Proxy(ui, {
                // read through the service itself, so a resize still re-renders
                get: (target, key) => {
                    if (key !== "size") {
                        return target[key];
                    }
                    if (chatterBelow()) {
                        return Math.min(target.size, SIZES.XL);
                    }
                    return chatterBeside(target.size) ? SIZES.XXL : target.size;
                },
            });
        }
    },

    hasFileViewer() {
        if (this.omRealUi && position() === "side" && this.omRealUi.size < SIZES.XXL) {
            return false;
        }
        return super.hasFileViewer(...arguments);
    },
});

patch(FormController.prototype, {
    get className() {
        const result = super.className;
        if (chatterBelow()) {
            delete result["o_xxl_form_view h-100"];
        } else if (!this.env.inDialog && this.ui.size < SIZES.XXL && chatterBeside(this.ui.size)) {
            // the row layout of an extra wide screen, on a large one too
            result["o_xxl_form_view h-100 o_om_chatter_beside"] = true;
        }
        return result;
    },
});
