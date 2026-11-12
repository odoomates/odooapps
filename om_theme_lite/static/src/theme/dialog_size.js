import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";
import { session } from "@web/session";

/**
 * A full screen button in the header of every large dialog, and a per-user choice
 * to open them full screen.
 *
 * Small confirmation dialogs keep their size: making "Are you sure?" fill the
 * screen helps nobody.
 */
patch(Dialog.prototype, {
    setup() {
        super.setup(...arguments);
        if (session.om_dialog_size === "full" && this.omCanResize) {
            this.dialogSize.set("fs");
        }
    },

    get omCanResize() {
        return this.design !== "minimal" && !this.isFullscreen;
    },

    get omIsMaximized() {
        return this.size === "fs";
    },

    omToggleSize() {
        if (this.omIsMaximized) {
            this.dialogSize.set(this.omSizeBefore);
        } else {
            this.omSizeBefore = this.dialogSize();
            this.dialogSize.set("fs");
        }
    },
});
