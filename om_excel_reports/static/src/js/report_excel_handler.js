import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { download } from "@web/core/network/download";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { getReportUrl } from "@web/webclient/actions/reports/utils";
import { ExcelChoiceDialog } from "./excel_choice_dialog";

const reportInfoCache = new Map();

/** {allowed, ask} for a PDF report: may it be exported, and should we ask the user? */
function getReportInfo(reportName) {
    if (!reportInfoCache.has(reportName)) {
        const promise = rpc("/om_excel_reports/excel_allowed", { report_name: reportName });
        promise.catch(() => reportInfoCache.delete(reportName));
        reportInfoCache.set(reportName, promise);
    }
    return reportInfoCache.get(reportName);
}

/** Downloads the Excel version of a report action through the report controller. */
async function downloadExcel(action, env) {
    const url = getReportUrl(action, "excel");
    const context = { ...user.context, ...(action.context || {}) };
    env.services.ui.block();
    try {
        await download({
            url: "/report/download",
            data: {
                data: JSON.stringify([url, "excel"]),
                context: JSON.stringify(context),
            },
        });
    } finally {
        env.services.ui.unblock();
    }
}

/** URL showing the PDF inline, under its real file name (see controller). */
function previewUrl(action) {
    const context = { ...user.context, ...(action.context || {}) };
    const params = new URLSearchParams();
    let url = `/om_excel_reports/preview/${action.report_name}`;
    if (action.data && JSON.stringify(action.data) !== "{}") {
        params.set("options", JSON.stringify(action.data));
    } else if (context.active_ids?.length) {
        url += `/${context.active_ids.join(",")}`;
    }
    params.set("context", JSON.stringify(context));
    return `${url}?${params.toString()}`;
}

/** Opens the PDF in a new tab. Returns false when the browser blocked the pop-up. */
function openPreview(action, env) {
    const win = browser.open(previewUrl(action), "_blank");
    if (!win) {
        env.services.notification.add(
            _t("Your browser blocked the preview tab. Allow pop-ups for this site to preview reports; the PDF is downloaded instead."),
            { type: "warning" }
        );
        return false;
    }
    return true;
}

/** Resolves with "pdf" | "excel" | "both" | "preview", or null when the dialog is dismissed. */
function askChoice(env, action) {
    return new Promise((resolve) => {
        env.services.dialog.add(
            ExcelChoiceDialog,
            {
                title: action.name || action.display_name || action.report_name,
                onChoice: (choice) => resolve(choice),
            },
            { onClose: () => resolve(null) }
        );
    });
}

/**
 * Registered in the "ir.actions.report handlers" registry. Returning true means the
 * action was fully handled; returning false lets Odoo continue (PDF download).
 */
async function excelReportHandler(action, options, env) {
    if (!action.report_type?.startsWith("qweb-pdf")) {
        return false;
    }
    const info = await getReportInfo(action.report_name);
    if (!info.allowed || !info.ask) {
        return false;
    }
    const choice = await askChoice(env, action);
    if (choice === null) {
        return true; // dialog dismissed: print nothing
    }
    if (choice === "pdf") {
        return false;
    }
    if (choice === "preview") {
        return openPreview(action, env); // false (pop-up blocked) falls back to the download
    }
    await downloadExcel(action, env);
    return choice === "excel"; // "both" falls through to the regular PDF download
}

registry
    .category("ir.actions.report handlers")
    .add("om_excel_reports.handler", excelReportHandler, { sequence: 1 });
