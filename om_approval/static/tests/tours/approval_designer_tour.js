import { registry } from "@web/core/registry";

// A flow opened in the designer: a step for given people added, saved and activated.
registry.category("web_tour.tours").add("om_approval_designer", {
    steps: () => [
        {
            content: "open the designer from the form",
            trigger: 'button[name="action_open_designer"]',
            run: "click",
        },
        {
            content: "the chain shows the button and the first step",
            trigger: '.o_approval_card_trigger:contains("When Archive is clicked")',
        },
        {
            content: "add a step after the first one",
            trigger: ".o_approval_insert:eq(1) .o_approval_insert_button",
            run: "click",
        },
        {
            content: "name it",
            trigger: ".o_approval_designer_panel .o_approval_step_name",
            run: "edit Tour Step",
        },
        {
            content: "approved by specific people",
            trigger: '.o_approval_designer_panel .o_approval_segments button:contains("Specific People")',
            run: "click",
        },
        {
            content: "the card says who is missing",
            trigger: '.o_approval_card_error:contains("Choose the people approving")',
        },
        {
            content: "search a user",
            trigger: ".o_approval_designer_panel .o-autocomplete--input",
            run: "edit Mitchell",
        },
        {
            content: "choose Mitchell Admin",
            trigger: '.o-autocomplete--dropdown-item:contains("Mitchell Admin")',
            run: "click",
        },
        {
            content: "the summary names him",
            trigger: '.o_approval_designer_summary:contains("Tour Step"):contains("Mitchell Admin")',
        },
        {
            content: "all of them approve",
            trigger: '.o_approval_designer_panel .o_approval_modes button:contains("All of Them")',
            run: "click",
        },
        {
            content: "the card says so",
            trigger: '.o_approval_card_selected:contains("all of them")',
        },
        {
            content: "remind after 2 days",
            trigger: ".o_approval_designer_panel .o_approval_remind_days",
            run: "edit 2 && press Tab",
        },
        {
            content: "the card shows the reminder",
            trigger: '.o_approval_card_selected:contains("reminded after 2 d")',
        },
        {
            content: "activate the flow, which saves it",
            trigger: ".o_approval_designer_activate",
            run: "click",
        },
        {
            content: "the flow is active",
            trigger: '.o_approval_designer_toolbar .badge:contains("Active")',
        },
        {
            content: "test it on a record, once saved",
            trigger: '.o_approval_designer_toolbar:not(:has(.badge:contains("Unsaved"))) .o_approval_designer_test:enabled',
            run: "click",
        },
        {
            content: "the test says who would approve",
            trigger: '.modal:contains("it would wait for"):contains("Tour Step")',
        },
        {
            content: "close the test",
            trigger: '.modal button:contains("Close")',
            run: "click",
        },
        {
            content: "back on the designer",
            trigger: "body:not(:has(.modal)) .o_approval_designer",
        },
        {
            content: "open the trigger card",
            trigger: ".o_approval_card_trigger",
            run: "click",
        },
        {
            content: "open the Amount section",
            trigger: '.o_approval_section_head[data-section="amount"]',
            run: "click",
        },
        {
            content: "the Amount section is open",
            trigger: ".o_approval_amount .o_approval_section_body",
        },
        {
            content: "close the Button section",
            trigger: '.o_approval_section_head[data-section="button"]',
            run: "click",
        },
        {
            content: "the Button section is closed, Amount still open",
            trigger: ".o_approval_designer_panel:not(:has(.o_approval_buttons)) .o_approval_amount .o_approval_section_body",
        },
        {
            content: "insert a step before the first one",
            trigger: ".o_approval_insert:eq(0) .o_approval_insert_button",
            run: "click",
        },
        {
            content: "the new step is the first of three",
            trigger: '.o_approval_designer_panel .o_approval_eyebrow:contains("Step 1 of 3")',
        },
        {
            content: "the step that was first is second now",
            trigger: '.o_approval_card_step:eq(1):contains("First")',
        },
    ],
});
