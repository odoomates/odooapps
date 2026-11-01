import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("om_excel_reports_pdf_dialog", {
    steps: () => [
        {
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
            },
        },
        {
            trigger: ".o_list_view .o_data_row:first-child .o_list_record_selector input",
            run: "click",
        },
        {
            trigger: ".o_cp_action_menus button:contains('Print')",
            run: "click",
        },
        {
            // The PDF entry opens the chooser.
            trigger: ".o-dropdown-item:contains('Model Overview')",
            run: "click",
        },
        {
            trigger: ".o_report_excel_choice .o_rec_title:contains('Model Overview')",
        },
        {
            trigger: ".o_report_excel_choice .o_rec_tile_primary[data-choice='excel']",
            run: "click",
        },
        {
            trigger: "body[data-excel-done='1']:not([data-excel-error])",
            run: () => {
                const request = JSON.parse(document.body.dataset.excelRequest);
                if (!request[0].startsWith("/report/excel/base.report_irmodeloverview") || request[1] !== "excel") {
                    throw new Error("Unexpected download request: " + document.body.dataset.excelRequest);
                }
            },
        },
    ],
});
