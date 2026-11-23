import { patch } from "@web/core/utils/patch";
import { SIZES } from "@web/core/ui/ui_utils";
import { session } from "@web/session";
import { FormController } from "@web/views/form/form_controller";
import { FormRenderer } from "@web/views/form/form_renderer";

/**
 * Where the chatter sits on a form, chosen by each user in My Preferences.
 *
 * Odoo lays a form out in a row on wide screens (1400 pixels), with the chatter (or an
 * attachment preview) beside the sheet, and in a column below that.
 *
 * "Below the form": the chatter stays underneath even on a wide screen. Moving only
 * the chatter would leave it stretched beside the form in that row, so a wide screen
 * is laid out the way Odoo lays out a normal one: the wide-screen class is dropped,
 * and every side-by-side layout becomes its below-the-form equivalent.
 *
 * "Beside the form": the chatter stays next to the form from a large screen (992 pixels)
 * up, where Odoo would put it underneath. Phones and small tablets keep Odoo's own
 * layout: there is no room beside the form there. On a wide screen a document
 * with an attachment preview keeps the preview beside the form, as Odoo shows it.
 */
const position = () => session.om_chatter_position || "auto";
const chatterBelow = () => position() === "bottom";
const chatterBeside = (size) => position() === "side" && size >= SIZES.LG;

// The form template picks its row layout from the screen size alone, so the
// stacking itself is done in CSS, under this class (see chatter_position.scss).
document.documentElement.classList.toggle("o_om_chatter_below", chatterBelow());

patch(FormRenderer.prototype, {
    mailLayout() {
        const layout = super.mailLayout(...arguments);
        if (chatterBelow()) {
            return {
                SIDE_CHATTER: "BOTTOM_CHATTER",
                COMBO: "BOTTOM_CHATTER",
                EXTERNAL_COMBO_XXL: "EXTERNAL_COMBO",
            }[layout] || layout;
        }
        if (chatterBeside(this.uiService.size)) {
            return {
                BOTTOM_CHATTER: "SIDE_CHATTER",
                EXTERNAL_COMBO: "EXTERNAL_COMBO_XXL",
            }[layout] || layout;
        }
        return layout;
    },
});

patch(FormController.prototype, {
    get className() {
        const result = super.className;
        if (chatterBelow()) {
            delete result["o_xxl_form_view h-100"];
        } else if (!this.env.inDialog && this.ui.size < SIZES.XXL && chatterBeside(this.ui.size)) {
            // the row layout of a wide screen, on a large one too
            result["o_xxl_form_view h-100 o_om_chatter_beside"] = true;
        }
        return result;
    },
});
