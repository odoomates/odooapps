/** @odoo-module **/

import { registry } from "@web/core/registry";

// From the user form into a preview of that user, and back.
registry.category("web_tour.tours").add("om_access_manager_preview", {
    test: true,
    steps: () => [
        {
            content: "preview the user",
            trigger: 'button[name="action_om_preview"]',
            run: "click",
        },
        {
            content: "the web client is shown as the user",
            trigger: "body.o_om_preview .o_om_preview_banner",
            isCheck: true,
        },
        {
            content: "the user's own home page, not the screen of the administrator",
            trigger: "body.o_om_preview .o_main_navbar",
            async run() {
                await new Promise((resolve) => setTimeout(resolve, 1000));
                if (document.querySelector(".modal .o_error_dialog, .o_dialog .modal-body")) {
                    throw new Error("the preview opened on an error");
                }
            },
        },
        {
            content: "exit the preview",
            trigger: ".o_om_preview_banner button",
            run: "click",
        },
        {
            content: "back on the user form, as the administrator",
            trigger: 'body:not(.o_om_preview) button[name="action_om_preview"]',
            isCheck: true,
        },
    ],
});
