import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";
import { session } from "@web/session";

import { useState } from "@odoo/owl";

// the sizes worth a full screen button: a small confirmation keeps its size
const LARGE_SIZES = ["lg", "xl"];

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
        this.omSize = useState({
            maximized: session.om_dialog_size === "full" && this.omCanResize,
        });
    },

    get omCanResize() {
        return this.props.header && LARGE_SIZES.includes(this.props.size) && !this.isFullscreen;
    },

    get omIsMaximized() {
        return this.omSize.maximized;
    },

    /** The size the dialog is drawn at: its own, or full screen. */
    get omDialogSize() {
        return this.omIsMaximized ? "fs" : this.props.size;
    },

    get contentStyle() {
        // a maximized dialog fills the screen, so where it was dragged to no longer applies
        return this.omIsMaximized ? "" : super.contentStyle;
    },

    omToggleSize() {
        this.omSize.maximized = !this.omSize.maximized;
    },
});
