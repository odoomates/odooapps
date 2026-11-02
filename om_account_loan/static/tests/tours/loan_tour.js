import { registry } from "@web/core/registry";

// Create a loan, confirm it, draw it down, compute the schedule and pay the first instalment.
registry.category("web_tour.tours").add("om_account_loan_tour", {
    steps: () => [
        {
            content: "create a loan",
            trigger: ".o_list_button_add",
            run: "click",
        },
        {
            content: "the lender",
            trigger: ".o_field_widget[name=partner_id] input",
            run: "edit Tour Lending",
        },
        {
            content: "pick the lender",
            trigger: ".o-autocomplete--dropdown-item:contains(Tour Lending Bank)",
            run: "click",
        },
        {
            content: "the principal",
            trigger: ".o_field_widget[name=principal] input",
            run: "edit 24000",
        },
        {
            content: "the number of payments",
            trigger: ".o_field_widget[name=payment_count] input",
            run: "edit 24",
        },
        {
            content: "the rate",
            trigger: ".o_field_widget[name=rate] input",
            run: "edit 7.5",
        },
        {
            content: "confirm the loan",
            trigger: ".o_form_view button[name=action_confirm]",
            run: "click",
        },
        {
            content: "the loan runs, with its schedule",
            trigger: ".o_form_view .o_statusbar_status button.o_arrow_button_current:contains(Running)",
        },
        {
            content: "the projected schedule is listed",
            trigger: ".o_field_widget[name=line_ids] .o_data_row:nth-child(24)",
        },
        {
            content: "draw it down",
            trigger: ".o_form_view button[name=action_drawdown]",
            run: "click",
        },
        {
            content: "the whole principal is proposed",
            trigger: ".modal .o_field_widget[name=amount] input:value(24,000.00)",
        },
        {
            content: "post the drawdown",
            trigger: ".modal button[name=action_confirm]",
            run: "click",
        },
        {
            content: "the principal is drawn",
            trigger: "body:not(:has(.modal)) .o_form_view .o_field_widget[name=outstanding_amount]:contains(24,000.00)",
        },
        {
            content: "compute the schedule",
            trigger: ".o_form_view button[name=action_compute_schedule]",
            run: "click",
        },
        {
            content: "pay the first instalment",
            trigger: ".o_field_widget[name=line_ids] .o_data_row:first-child button[name=action_pay]",
            run: "click",
        },
        {
            content: "confirm the payment",
            trigger: ".modal button[name=action_confirm]",
            run: "click",
        },
        {
            content: "the first instalment is paid",
            trigger: "body:not(:has(.modal)) .o_field_widget[name=line_ids] .o_data_row:first-child .o_field_widget[name=state]:contains(Paid)",
        },
        {
            content: "the entries of the loan",
            trigger: ".o_form_view button[name=action_view_moves]:contains(2)",
        },
    ],
});
