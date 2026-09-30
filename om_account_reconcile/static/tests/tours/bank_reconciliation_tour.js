import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("om_bank_reconciliation_tour", {
    steps: () => [
        {
            content: "Select the transaction paying the invoice",
            trigger: ".o_om_bank_rec_transaction:contains(TOUR PAYMENT)",
            run: "click",
        },
        {
            content: "The invoice is suggested",
            trigger: ".o_om_bank_rec_match_row:contains(Tour Customer)",
        },
        {
            content: "Nothing is left on the suspense account",
            trigger: ".o_om_bank_rec_validate:contains(Validate):not(:contains(partial)):enabled",
            run: "click",
        },
        {
            content: "The reconciled transaction leaves the list",
            trigger: ".o_om_bank_rec_list:not(:has(.o_om_bank_rec_transaction:contains(TOUR PAYMENT)))",
        },
        {
            content: "Select the bank fee",
            trigger: ".o_om_bank_rec_transaction:contains(Tour bank fee)",
            run: "click",
        },
        {
            content: "Open the counterpart form",
            trigger: ".o_om_bank_rec_header:contains(Tour bank fee) ~ .nav-tabs a[data-tab=writeoff]",
            run: "click",
        },
        {
            content: "Choose the account",
            trigger: ".o_om_bank_rec_writeoff_form .o_record_selector input",
            run: "edit Tour Bank Charges",
        },
        {
            content: "Pick it in the dropdown",
            trigger: ".o-autocomplete--dropdown-item:contains(Tour Bank Charges)",
            run: "click",
        },
        {
            content: "Add the counterpart",
            trigger: ".o_om_bank_rec_add_writeoff",
            run: "click",
        },
        {
            content: "The counterpart is in the proposal",
            trigger: ".o_om_bank_rec_writeoff_row:contains(Tour Bank Charges)",
        },
        {
            content: "Validate the fee",
            trigger: ".o_om_bank_rec_validate:not(:contains(partial)):enabled",
            run: "click",
        },
        {
            content: "No transaction left to reconcile",
            trigger: ".o_om_bank_rec_list:not(:has(.o_om_bank_rec_transaction))",
        },
        {
            content: "Show the reconciled transactions",
            trigger: "button[data-filter=reconciled]",
            run: "click",
        },
        {
            content: "Select the bank fee again",
            trigger: ".o_om_bank_rec_transaction.o_reconciled:contains(Tour bank fee)",
            run: "click",
        },
        {
            content: "Undo its reconciliation",
            trigger: ".o_om_bank_rec_header:contains(Tour bank fee) ~ .o_om_bank_rec_undo",
            run: "click",
        },
        {
            content: "The fee can be reconciled again",
            trigger: ".o_om_bank_rec_header:contains(Tour bank fee) ~ .o_om_bank_rec_proposal .o_om_bank_rec_validate",
        },
    ],
});
