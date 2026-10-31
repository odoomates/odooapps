import { registry } from "@web/core/registry";

// A template opened in the editor: a signature field added for the second role, made optional, and saved.
registry.category("web_tour.tours").add("om_sign_template_editor", {
    steps: () => [
        {
            content: "open the editor from the form",
            trigger: 'button[name="action_open_editor"]',
            run: "click",
        },
        {
            content: "the pages of the PDF are shown",
            trigger: '.o_sign_page[data-page="2"] canvas.o_sign_page_canvas',
        },
        {
            content: "the field of the first role is on the first page",
            trigger: '.o_sign_page[data-page="1"] .o_sign_field[data-type="name"]',
        },
        {
            content: "add fields for the company",
            trigger: '.o_sign_role_choice:contains("Company")',
            run: "click",
        },
        {
            content: "add a signature to the page in view",
            trigger: '.o_sign_palette_item[data-type="signature"]',
            run: "click",
        },
        {
            content: "the field is selected, for the company",
            trigger: '.o_sign_field_selected[data-type="signature"]',
        },
        {
            content: "the panel shows it filled by the company",
            trigger: ".o_sign_field_role",
            run: function () {
                const select = document.querySelector(".o_sign_field_role");
                if (select.options[select.selectedIndex].text !== "Company") {
                    throw new Error("The new field is not for the company.");
                }
            },
        },
        {
            content: "label it",
            trigger: ".o_sign_field_label",
            run: "edit Company signature && press Tab",
        },
        {
            content: "the field shows its label",
            trigger: '.o_sign_field_selected:contains("Company signature")',
        },
        {
            content: "save",
            trigger: ".o_sign_editor_save",
            run: "click",
        },
        {
            content: "saved",
            trigger: '.o_sign_editor_toolbar:not(:has(.o_sign_status_dirty)):contains("2 field(s)")',
        },
        {
            content: "share it by a link",
            trigger: ".o_sign_editor_share",
            run: "click",
        },
        {
            content: "both roles are chosen when sending: it cannot be shared",
            trigger: ".o_sign_share_dialog .o_sign_share_problem",
        },
        {
            content: "the toggle is off",
            trigger: ".o_sign_share_dialog .o_sign_share_toggle:disabled:not(:checked)",
        },
        {
            content: "close",
            trigger: ".o_sign_share_dialog .modal-footer .btn-secondary",
            run: "click",
        },
        {
            content: "unselect the field: the roles are shown",
            trigger: ".o_sign_editor_canvas",
            run: "press Escape",
        },
        {
            content: "the person sending signs for the company",
            trigger: ".o_sign_role:eq(1) .o_sign_role_signer",
            run: "select requester",
        },
        {
            content: "share it again: saved first",
            trigger: ".o_sign_editor_share",
            run: "click",
        },
        {
            content: "share it",
            trigger: ".o_sign_share_dialog .o_sign_share_toggle:enabled:not(:checked)",
            run: "click",
        },
        {
            content: "the link to copy",
            trigger: '.o_sign_share_dialog .o_sign_share_url:value("/sign/share/")',
        },
        {
            content: "close",
            trigger: ".o_sign_share_dialog .modal-footer .btn-secondary",
            run: "click",
        },
        {
            content: "the editor shows it shared",
            trigger: ".o_sign_editor_share.active",
        },
    ],
});
