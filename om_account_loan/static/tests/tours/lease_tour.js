import { registry } from "@web/core/registry";

// Create a lease, confirm it (its liability is recognized) and bill the first payment.
registry.category("web_tour.tours").add("om_account_loan_lease_tour", {
    steps: () => [
        {
            content: "create a lease",
            trigger: ".o_list_button_add",
            run: "click",
        },
        {
            content: "the lessor",
            trigger: ".o_field_widget[name=partner_id] input",
            run: "edit Tour Lessor",
        },
        {
            content: "pick the lessor",
            trigger: ".o-autocomplete--dropdown-item:contains(Tour Lessor Properties)",
            run: "click",
        },
        {
            content: "the lease payment",
            trigger: ".o_field_widget[name=lease_payment] input",
            run: "edit 1000",
        },
        {
            content: "the number of payments",
            trigger: ".o_field_widget[name=payment_count] input",
            run: "edit 12",
        },
        {
            content: "the rate",
            trigger: ".o_field_widget[name=rate] input",
            run: "edit 6",
        },
        {
            content: "confirm the lease",
            trigger: ".o_form_view button[name=action_confirm]",
            run: "click",
        },
        {
            content: "the lease runs, recognized",
            trigger: ".o_form_view .o_statusbar_status button.o_arrow_button_current:contains(Running)",
        },
        {
            content: "the recognition entry",
            trigger: ".o_form_view button[name=action_view_moves]:contains(1)",
        },
        {
            content: "bill the first payment",
            trigger: ".o_field_widget[name=line_ids] .o_data_row:first-child button[name=action_create_bill]",
            run: "click",
        },
        {
            content: "the bill of the lessor",
            trigger: ".o_form_view .o_field_widget[name=partner_id]:contains(Tour Lessor Properties)",
        },
    ],
});
