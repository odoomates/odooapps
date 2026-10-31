import { registry } from "@web/core/registry";

// A signer of a template request fills in their fields on the pages of the document, from the emailed link: the
// signature typed in a script font and adopted, a text, a box ticked, and signs.
registry.category("web_tour.tours").add("om_sign_signing", {
    steps: () => [
        {
            content: "the pages of the document are drawn",
            trigger: '.o_sign_signing_page[data-page="2"] canvas.o_sign_signing_canvas[data-rendered]',
        },
        {
            content: "the name is filled in for the signer",
            trigger: '.o_sign_signing_field[data-type="name"] input:value("Acme Buyer")',
        },
        {
            content: "the required fields left to fill are counted",
            trigger: '.o_sign_signing_progress:contains("3 of 6 done")',
        },
        {
            content: "Finish waits for the required fields",
            trigger: ".o_sign_signing_finish:disabled",
        },
        {
            content: "start",
            trigger: '.o_sign_signing_next:contains("Start")',
            run: "click",
        },
        {
            content: "the signature is the first field to fill",
            trigger: '.o_sign_signing_field_active[data-type="signature"] button:focus',
            run: "click",
        },
        {
            content: "the signature is typed from the name",
            trigger: '.o_sign_field_dialog .o_web_sign_auto_button.active:contains("Type")',
        },
        {
            content: "or drawn, or uploaded",
            trigger: '.o_sign_field_dialog .o_web_sign_load_button:contains("Upload")',
        },
        {
            content: "adopt it",
            trigger: ".o_sign_field_dialog .o_sign_field_adopt:enabled",
            run: "click",
        },
        {
            content: "the signature is in its field",
            trigger: '.o_sign_signing_field[data-type="signature"]:not(.o_sign_signing_field_empty) img',
        },
        {
            content: "next field",
            trigger: '.o_sign_signing_next:contains("Next")',
            run: "click",
        },
        {
            content: "the job title is the next field to fill",
            trigger: '.o_sign_signing_field_active[data-type="text"] input:focus',
            run: "edit Head of Purchasing",
        },
        {
            content: "next field",
            trigger: ".o_sign_signing_next",
            run: "click",
        },
        {
            content: "tick the box",
            trigger: '.o_sign_signing_field_active[data-type="checkbox"] button[aria-checked="false"]',
            run: "click",
        },
        {
            content: "the box is ticked and everything is filled",
            trigger: '.o_sign_signing_field[data-type="checkbox"] button[aria-checked="true"]',
        },
        {
            content: "all done",
            trigger: '.o_sign_signing_progress:contains("6 of 6 done")',
        },
        {
            content: "finish",
            trigger: ".o_sign_signing_finish:enabled",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "signed: the others sign next",
            trigger: '.o_sign_signing_status:contains("You signed"):contains("The others sign next")',
        },
    ],
});
