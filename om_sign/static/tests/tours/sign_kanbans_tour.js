import { registry } from "@web/core/registry";

// The templates and the requests as cards: the first page of a template drawn on its card, the requests by status.
registry.category("web_tour.tours").add("om_sign_kanbans", {
    steps: () => [
        {
            content: "the template is a card",
            trigger: '.o_sign_template_kanban .o_kanban_record:contains("Kanban Tour Contract")',
        },
        {
            content: "its first page is drawn on the card",
            trigger:
                '.o_kanban_record:contains("Kanban Tour Contract") .o_sign_thumbnail img[src^="data:image/"]',
        },
        {
            content: "with its roles and its quick buttons",
            trigger:
                '.o_kanban_record:contains("Kanban Tour Contract"):has(.o_tag:contains("Customer")):has(button[name="action_send_bulk"])',
        },
        {
            content: "open the requests",
            trigger: '.o_main_navbar button:contains("Requests"), .o_main_navbar a:contains("Requests")',
            run: "click",
        },
        {
            content: "all the requests",
            trigger: '.dropdown-menu .dropdown-item:contains("All")',
            run: "click",
        },
        {
            content: "grouped by status",
            trigger: '.o_sign_request_kanban .o_kanban_group:contains("Waiting for Signatures")',
        },
        {
            content: "the request of the template, with its progress and its signers",
            trigger:
                '.o_kanban_group:contains("Waiting for Signatures") .o_kanban_record:contains("Kanban Tour Contract"):has(.o_progressbar):has(.o_sign_signer[data-state="to_sign"])',
        },
        {
            content: "open it",
            trigger: '.o_kanban_record:contains("Kanban Tour Contract")',
            run: "click",
        },
        {
            content: "the timeline of its signers",
            trigger: '.o_sign_timeline .o_sign_timeline_signer[data-state="to_sign"]:contains("Acme Buyer")',
        },
    ],
});
