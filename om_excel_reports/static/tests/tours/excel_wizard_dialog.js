/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("om_excel_reports_wizard_dialog", {
    steps: () => [
        {
            // Record download requests, then run a wizard-style report action.
            trigger: ".o_list_view",
            run: () => {
                const { download } = odoo.loader.modules.get("@web/core/network/download");
                const original = download._download;
                download._download = (options) => {
                    document.body.dataset.excelRequest = options.data.data;
                    return original(options).then(
                        () => {
                            document.body.dataset.excelDone = "1";
                        },
                        () => {
                            document.body.dataset.excelError = "1";
                        }
                    );
                };
                const env = odoo.__WOWL_DEBUG__.root.env;
                env.services.action.doAction({
                    type: "ir.actions.report",
                    report_type: "qweb-pdf",
                    report_name: "om_excel_reports.test_wizard_report",
                    name: "Excel Test Wizard Report",
                    data: { some_option: 1 },
                    context: {},
                });
            },
        },
        {
            trigger: ".o_report_excel_choice .o_rec_title:contains('Excel Test Wizard Report')",
        },
        {
            trigger: ".o_report_excel_choice .o_rec_tile_primary[data-choice='excel']",
            run: "click",
        },
        {
            trigger: "body[data-excel-done='1']:not([data-excel-error])",
            run: () => {
                const request = JSON.parse(document.body.dataset.excelRequest);
                if (
                    !request[0].startsWith("/report/excel/om_excel_reports.test_wizard_report?options=") ||
                    request[1] !== "excel"
                ) {
                    throw new Error("Unexpected download request: " + document.body.dataset.excelRequest);
                }
            },
        },
    ],
});
