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
 * screen is extra wide (1400 pixels), and both the form controller and the form
 * renderer decide that from the screen size they read off the ui service.
 *
 * "Below the form": they are handed a screen size capped just under that, so a
 * wide screen is laid out the way Odoo lays out a normal one: chatter below, no
 * preview beside it, and the wide-screen class dropped.
 *
 * "Beside the form": from a large screen (992 pixels) up, they are handed the
 * extra wide size, so the chatter sits beside the form where Odoo would put it
 * underneath. Phones and small tablets keep Odoo's own layout: there is no room
 * beside the form there. The attachment preview stays where Odoo shows it: beside
 * the form on an extra wide screen only.
 */
const position = () => session.om_chatter_position || "auto";
const chatterBelow = () => position() === "bottom";
const chatterBeside = (size) => position() === "side" && size >= SIZES.LG;
const changed = () => chatterBelow() || position() === "side";

// The stacking on a wide screen is done in CSS, under this class (see
// chatter_position.scss).
document.documentElement.classList.toggle("o_om_chatter_below", chatterBelow());

function sizedUi(ui) {
    return new Proxy(ui, {
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

patch(FormRenderer.prototype, "om_chatter_position", {
    setup() {
        this._super(...arguments);
        if (changed() && this.uiService) {
            this.uiService = sizedUi(this.uiService);
        }
    },
});

patch(FormController.prototype, "om_chatter_position", {
    setup() {
        this._super(...arguments);
        if (changed()) {
            this.omRealUi = this.ui;
            if (this.uiService) {
                this.uiService = sizedUi(this.uiService);
            }
            this.ui = sizedUi(this.ui);
        }
    },

    hasAttachmentViewer() {
        if (position() === "side" && this.omRealUi && this.omRealUi.size < SIZES.XXL) {
            return false;
        }
        return this._super(...arguments);
    },

    get className() {
        const result = this._super(...arguments);
        const realSize = this.omRealUi && this.omRealUi.size;
        if (!this.env.inDialog && realSize < SIZES.XXL && chatterBeside(realSize)) {
            result.o_om_chatter_beside = true;
        }
        return result;
    },
});
