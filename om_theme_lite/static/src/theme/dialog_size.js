/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";
import LegacyDialog from "web.Dialog";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";

const { useState } = owl.hooks;

// the sizes worth a full screen button: a small confirmation keeps its size
const LARGE_SIZES = ["modal-lg", "modal-xl"];
const LEGACY_LARGE_SIZES = ["large", "extra-large"];

const fullByDefault = () => session.om_dialog_size === "full";

/**
 * A full screen button in the header of every large dialog, and a per-user choice
 * to open them full screen.
 *
 * Small confirmation dialogs keep their size: making "Are you sure?" fill the
 * screen helps nobody.
 */
patch(Dialog.prototype, "om_theme_lite.dialog_size", {
    setup() {
        this._super(...arguments);
        // null until the button is used: the dialog's size is only known once
        // subclasses such as the action dialog have set it after this setup
        this.omSize = useState({ maximized: null });
    },

    omCanResize() {
        return this.renderHeader && LARGE_SIZES.includes(this.size) && !this.fullscreen;
    },

    omIsMaximized() {
        if (!this.omCanResize()) {
            return false;
        }
        return this.omSize.maximized === null ? fullByDefault() : this.omSize.maximized;
    },

    /** The classes the dialog is drawn with: its own size, or full screen. */
    omDialogClass() {
        return this.omIsMaximized() ? `${this.size} o_om_modal_fullscreen` : this.size;
    },

    omToggleSize() {
        this.omSize.maximized = !this.omIsMaximized();
    },
});

/**
 * The same for the dialogs the older views open: a record picked in a pop-up, the
 * "Search more" list, and the like.
 */
LegacyDialog.include({
    willStart() {
        return this._super(...arguments).then(() => {
            if (!this.renderHeader || !LEGACY_LARGE_SIZES.includes(this.size) || this.fullscreen) {
                return;
            }
            const $dialog = this.$modal.find(".modal-dialog");
            const $button = $("<button>", {
                type: "button",
                class: "btn fa o_om_dialog_size",
                tabindex: "-1",
                "aria-label": _t("Full screen"),
            });
            const apply = (maximized) => {
                $dialog.toggleClass("o_om_modal_fullscreen", maximized);
                $button.toggleClass("fa-compress", maximized).toggleClass("fa-expand", !maximized);
                $button.attr("title", maximized ? _t("Restore") : _t("Full screen"));
            };
            $button.on("click", () => apply(!$dialog.hasClass("o_om_modal_fullscreen")));
            this.$modal.find(".modal-header").append($button);
            apply(fullByDefault());
        });
    },
});
