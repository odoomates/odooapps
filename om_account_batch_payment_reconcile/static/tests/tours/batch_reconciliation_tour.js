import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("om_batch_reconciliation_tour", {
    steps: () => [
        {
            content: "Select the transaction of the payment run",
            trigger: ".o_om_bank_rec_transaction:contains(TOUR RUN)",
            run: "click",
        },
        {
            content: "Two batches have the amount: nothing is guessed, open the batches",
            trigger: ".o_om_bank_rec_header:contains(TOUR RUN) ~ .nav-tabs a[data-tab=batches]:contains(2)",
            run: "click",
        },
        {
            content: "Add the first batch",
            trigger: ".o_om_bank_rec_batch:first",
            run: "click",
        },
        {
            content: "Its two payments are in the proposal",
            trigger: ".o_om_bank_rec_proposal:has(.o_om_bank_rec_match_row + .o_om_bank_rec_match_row)",
        },
        {
            content: "Nothing is left on the suspense account",
            trigger: ".o_om_bank_rec_validate:contains(Validate):not(:contains(partial)):enabled",
            run: "click",
        },
        {
            content: "The reconciled transaction leaves the list",
            trigger: ".o_om_bank_rec_list:not(:has(.o_om_bank_rec_transaction:contains(TOUR RUN)))",
        },
    ],
});
