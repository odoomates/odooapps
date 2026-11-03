/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("om_excel_reports_preview_dialog", {
    steps: () => [
        {
            // Capture window.open instead of really opening a tab.
            trigger: ".o_list_view",
            run: () => {
                const { browser } = odoo.loader.modules.get("@web/core/browser/browser");
                browser.open = (url, target) => {
                    document.body.dataset.previewUrl = url;
                    document.body.dataset.previewTarget = target;
                    return {};
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
            trigger: ".o-dropdown-item:contains('Model Overview'):not(:contains('Excel'))",
            run: "click",
        },
        {
            trigger: ".o_report_excel_choice .o_rec_preview",
            run: "click",
        },
        {
            trigger: "body[data-preview-url]:not(:has(.o_report_excel_choice))",
            run: () => {
                const url = document.body.dataset.previewUrl;
                if (
                    !url.startsWith("/om_excel_reports/preview/base.report_irmodeloverview/") ||
                    !url.includes("context=") ||
                    document.body.dataset.previewTarget !== "_blank"
                ) {
                    throw new Error("Unexpected preview URL: " + url);
                }
            },
        },
    ],
});
