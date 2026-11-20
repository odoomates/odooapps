import { registry } from "@web/core/registry";

// A visitor of the shared link of a template: their name and email, the code emailed to them, then they sign the
// document made for them, straight away. The code is the one the test gives.
registry.category("web_tour.tours").add("om_sign_share", {
    steps: () => [
        {
            content: "the name of the visitor",
            trigger: "#o_sign_share_name",
            run: "edit Vera Visitor",
        },
        {
            content: "their email",
            trigger: "#o_sign_share_email",
            run: "edit vera@example.com",
        },
        {
            content: "ask for the code",
            trigger: ".o_sign_share_start button[type=submit]",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "the code is sent",
            trigger: '.o_sign_share_sent:contains("vera@example.com")',
        },
        {
            content: "enter it",
            trigger: "#o_sign_share_code",
            run: "edit 123456",
        },
        {
            content: "confirm",
            trigger: ".o_sign_share_verify button[type=submit]",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "the document to sign is shown",
            trigger: '.o_sign_signing_page[data-page="2"] canvas.o_sign_signing_canvas[data-rendered]',
        },
        {
            content: "the name is the visitor's",
            trigger: '.o_sign_signing_field[data-type="name"] input:value("Vera Visitor")',
        },
        {
            content: "start",
            trigger: '.o_sign_signing_next:contains("Start")',
            run: "click",
        },
        {
            content: "sign",
            trigger: '.o_sign_signing_field_active[data-type="signature"] button:focus',
            run: "click",
        },
        {
            content: "the signature is typed from the name",
            trigger: '.o_sign_field_dialog .o_web_sign_auto_button.active:contains("Type")',
        },
        {
            content: "adopt it",
            trigger: ".o_sign_field_dialog .o_sign_field_adopt:enabled",
            run: "click",
        },
        {
            content: "finish",
            trigger: ".o_sign_signing_finish:enabled",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "signed: the document with the signature, read-only",
            trigger: '.o_sign_signing_readonly .o_sign_signing_other[data-type="signature"] img',
        },
        {
            content: "the others sign next",
            trigger: '.o_sign_signing_status:contains("You signed"):contains("The others sign next")',
        },
    ],
});

// A copy recipient opens their link: the document with the fields signed so far, nothing to fill.
registry.category("web_tour.tours").add("om_sign_readonly", {
    steps: () => [
        {
            content: "the pages are drawn",
            trigger: '.o_sign_signing_page[data-page="2"] canvas.o_sign_signing_canvas[data-rendered]',
        },
        {
            content: "where it stands",
            trigger: '.o_sign_signing_status:contains("You receive a copy"):contains("1 of 2 signed")',
        },
        {
            content: "the signature of the customer",
            trigger: '.o_sign_signing_page[data-page="1"] .o_sign_signing_other[data-type="signature"] img',
        },
        {
            content: "nothing to fill, nothing to finish",
            trigger: ".o_sign_signing:not(:has(.o_sign_signing_field)):not(:has(.o_sign_signing_finish))",
        },
        {
            content: "the document can be downloaded",
            trigger: '.o_sign_signing_download_button[href$="/document?download=1"]',
        },
    ],
});
