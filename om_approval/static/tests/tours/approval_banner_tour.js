/** @odoo-module **/

import tour from "web_tour.tour";

// A step running nothing only checks. A trigger naming .modal looks in the whole page (in_modal: false):
// otherwise the tour looks for it inside the open dialog.

// A contact waiting for the approval of its archiving: the banner, the read-only form, then the approval.
tour.register("om_approval_banner", { test: true }, [
    {
        content: "the banner says what the record waits for",
        trigger: '.o_approval_banner:contains("Archive"):contains("waits for approval"):contains("Tour Approvers")',
        run() {},
    },
    {
        content: "the banner says the record is locked",
        trigger: '.o_approval_banner:contains("read-only until Archive has run")',
        run() {},
    },
    {
        content: "the form is read-only",
        trigger: ".o_form_view .o_form_readonly",
        run() {},
    },
    {
        content: "open the steps",
        trigger: '.o_approval_banner button:contains("Details")',
        run: "click",
    },
    {
        content: "the steps are listed",
        trigger: ".o_approval_banner_steps td:contains(Tour Approvers)",
        run() {},
    },
    {
        content: "approve",
        trigger: '.o_approval_banner button:contains("Approve")',
        run: "click",
    },
    {
        content: "write the optional note",
        trigger: '.modal .o_field_widget[name="note"] textarea',
        in_modal: false,
        run: "text Fine by me",
    },
    {
        content: "confirm the approval",
        trigger: '.modal button[name="action_confirm"]:contains("Approve")',
        in_modal: false,
        run: "click",
    },
    {
        content: "the banner is gone once the button ran",
        trigger: "body:not(:has(.modal)) .o_form_view:not(:has(.o_approval_banner)) .o_field_widget[name=name]",
        run() {},
    },
    {
        content: "the form is editable again",
        trigger: "body:not(:has(.modal)) .o_form_view .o_form_editable .o_field_widget[name=name] input",
        run() {},
    },
]);
