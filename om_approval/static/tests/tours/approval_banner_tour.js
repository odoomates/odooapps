import { registry } from "@web/core/registry";

// A contact waiting for the approval of its archiving: the banner, the read-only form, then the approval.
registry.category("web_tour.tours").add("om_approval_banner", {
    steps: () => [
        {
            content: "the banner says what the record waits for",
            trigger: '.o_approval_banner:contains("Archive"):contains("waits for approval"):contains("Tour Approvers")',
        },
        {
            content: "the banner says the record is locked",
            trigger: '.o_approval_banner:contains("read-only until Archive has run")',
        },
        {
            content: "the form is read-only",
            trigger: ".o_form_view .o_form_readonly",
        },
        {
            content: "open the steps",
            trigger: '.o_approval_banner button:contains("Details")',
            run: "click",
        },
        {
            content: "the steps are listed",
            trigger: ".o_approval_banner_steps td:contains(Tour Approvers)",
        },
        {
            content: "approve",
            trigger: '.o_approval_banner button:contains("Approve")',
            run: "click",
        },
        {
            content: "write the optional note",
            trigger: '.modal .o_field_widget[name="note"] textarea',
            run: "edit Fine by me",
        },
        {
            content: "confirm the approval",
            trigger: '.modal button[name="action_confirm"]:contains("Approve")',
            run: "click",
        },
        {
            content: "the banner is gone once the button ran",
            trigger: "body:not(:has(.modal)) .o_form_view:not(:has(.o_approval_banner)) .o_field_widget[name=name]",
        },
        {
            content: "the form is editable again",
            trigger: "body:not(:has(.modal)) .o_form_view .o_form_editable .o_field_widget[name=name] input",
        },
    ],
});
