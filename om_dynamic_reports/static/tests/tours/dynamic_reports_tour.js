import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("om_dynamic_reports_tour", {
    steps: () => [
        {
            content: "the general ledger shows its accounts",
            trigger: ".o_omr_report .o_omr_table tbody tr.o_omr_row_leaf",
        },
        {
            content: "unfold the first account",
            trigger: ".o_omr_table tbody tr.o_omr_row_leaf.o_omr_clickable:first",
            run: "click",
        },
        {
            content: "its journal items appear",
            trigger: ".o_omr_table tbody tr.o_omr_row_detail",
        },
        {
            content: "the total sticks at the bottom",
            trigger: ".o_omr_table tfoot tr.o_omr_row_total",
        },
        {
            content: "open the report switcher",
            trigger: ".o_omr_switcher",
            run: "click",
        },
        {
            content: "switch to the trial balance",
            trigger: ".o_omr_switcher_menu .o_omr_report_item:contains('Trial Balance')",
            run: "click",
        },
        {
            content: "the trial balance has its column groups",
            trigger: ".o_omr_table thead tr.o_omr_head_groups th.o_omr_head_group:contains('Ending Balance')",
        },
        {
            content: "open the options",
            trigger: ".o_omr_filters button:contains('Options')",
            run: "click",
        },
        {
            content: "group the accounts by type",
            trigger: ".o_omr_options_menu .dropdown-item:contains('Account type')",
            run: "click",
        },
        {
            content: "the accounts are grouped",
            trigger: ".o_omr_table tbody tr.o_omr_row_group",
        },
        {
            content: "back to the accounts without grouping",
            trigger: ".o_omr_options_menu .dropdown-item:contains('No grouping')",
            run: "click",
        },
        {
            content: "a figure of an account opens what makes it",
            trigger: ".o_omr_table tbody tr.o_omr_row_leaf td.o_omr_cell_drill:first",
            run: "click",
        },
        {
            content: "the journal items of that figure",
            trigger: ".o_list_view .o_data_row",
        },
    ],
});
