#!/usr/bin/env python3
""" Write the sample dashboards, shown by the Dashboards app to the databases that have no data yet.

A sample is the dashboard with the values it shows on a database with demo data, and no formula nor data source.
Run it against an Odoo server with demo data and the dashboards installed (om_account_accountant), e.g.:

    python3 om_spreadsheet_account/tools/export_samples.py http://localhost:8069 admin admin

Needs Playwright (pip install playwright && playwright install chromium). Not loaded by Odoo.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# dashboard name: (module, sample file)
SAMPLES = {
    'Accounting Overview': ('om_spreadsheet_account', 'accounting_overview_sample_dashboard.json'),
    'Profit and Loss': ('om_spreadsheet_account', 'profit_and_loss_sample_dashboard.json'),
    'Balance Sheet': ('om_spreadsheet_account', 'balance_sheet_sample_dashboard.json'),
    'Receivables and Payables': ('om_spreadsheet_account', 'receivables_payables_sample_dashboard.json'),
    'Bank and Cash': ('om_spreadsheet_account', 'bank_cash_sample_dashboard.json'),
    'Assets': ('om_spreadsheet_account_asset', 'assets_sample_dashboard.json'),
    'Budgets': ('om_spreadsheet_account_budget', 'budgets_sample_dashboard.json'),
    'Follow-ups and Cash Forecast': ('om_spreadsheet_account_followup', 'followups_forecast_sample_dashboard.json'),
}

EXPORT_JS = r"""
async (name) => {
    const { helpers } = odoo.loader.modules.get("@odoo/o-spreadsheet");
    const loader = odoo.__WOWL_DEBUG__.root.env.services.spreadsheet_dashboard_loader;
    const model = loader.getActiveDashboard().model;
    const isLoading = () => model.getters.getSheetIds().some((sheetId) => {
        for (let row = 0; row < model.getters.getNumberRows(sheetId); row++) {
            for (let col = 0; col < model.getters.getNumberCols(sheetId); col++) {
                const cell = model.getters.getEvaluatedCell({ sheetId, col, row });
                if (cell.type === "error" && String(cell.message || cell.value).includes("Loading")) {
                    return true;
                }
            }
        }
        return false;
    });
    for (let attempt = 0; attempt < 150 && isLoading(); attempt++) {
        await new Promise((resolve) => setTimeout(resolve, 200));
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));

    const data = model.exportData();
    const formatIds = Object.fromEntries(Object.entries(data.formats || {}).map(([id, fmt]) => [fmt, id]));
    const formatId = (fmt) => {
        if (!formatIds[fmt]) {
            const id = String(Object.keys(data.formats).length + 1);
            data.formats[id] = fmt;
            formatIds[fmt] = id;
        }
        return Number(formatIds[fmt]);
    };
    // every value on screen becomes a plain cell, the spilled tables included
    for (const sheet of data.sheets) {
        const cells = {};
        for (let row = 0; row < model.getters.getNumberRows(sheet.id); row++) {
            for (let col = 0; col < model.getters.getNumberCols(sheet.id); col++) {
                const cell = model.getters.getEvaluatedCell({ sheetId: sheet.id, col, row });
                if (cell.type === "empty" || cell.type === "error" || cell.value === "" || cell.value === null) {
                    continue;
                }
                const xc = helpers.toXC(col, row);
                cells[xc] = typeof cell.value === "boolean" ? (cell.value ? "TRUE" : "FALSE") : String(cell.value);
                if (cell.format && !(sheet.formats || {})[xc]) {
                    sheet.formats = sheet.formats || {};
                    sheet.formats[xc] = formatId(cell.format);
                }
            }
        }
        sheet.cells = cells;
    }
    // the charts reading the models read the values they show, written next to the data
    const dataSheet = data.sheets.find((sheet) => sheet.name === "Data");
    let column = 20;
    for (const sheet of data.sheets) {
        for (const figure of sheet.figures) {
            if (figure.tag !== "carousel") {
                continue;
            }
            for (const [chartId, definition] of Object.entries(figure.data.chartDefinitions || {})) {
                if (definition.dataSource?.type !== "odoo") {
                    continue;
                }
                const runtime = model.getters.getChartRuntime(chartId);
                const chartData = runtime?.chartJsConfig?.data || { labels: [], datasets: [] };
                const labels = chartData.labels || [];
                const values = chartData.datasets?.[0]?.data || [];
                labels.forEach((text, index) => {
                    dataSheet.cells[helpers.toXC(column, index)] = String(text);
                    dataSheet.cells[helpers.toXC(column + 1, index)] = String(values[index] ?? 0);
                });
                const last = Math.max(labels.length, 1) - 1;
                figure.data.chartDefinitions[chartId] = {
                    type: definition.type,
                    title: definition.title,
                    legendPosition: definition.legendPosition,
                    humanize: true,
                    dataSource: {
                        type: "range",
                        labelRange: `Data!${helpers.toXC(column, 0)}:${helpers.toXC(column, last)}`,
                        dataSets: [{ dataSetId: "0", dataRange: `Data!${helpers.toXC(column + 1, 0)}:${helpers.toXC(column + 1, last)}` }],
                        dataSetsHaveTitle: false,
                    },
                    dataSetStyles: {},
                };
                column += 2;
            }
            figure.data.fieldMatching = {};
        }
    }
    data.pivots = {};
    data.pivotNextId = 1;
    data.lists = {};
    data.listNextId = 1;
    data.globalFilters = [];
    return data;
}
"""


def main(url, login, password):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width': 1500, 'height': 1000})
        page.goto('%s/web/login' % url)
        page.fill('input[name=login]', login)
        page.fill('input[name=password]', password)
        page.click('button[type=submit]')
        page.wait_for_selector('.o_main_navbar', timeout=60000)
        page.goto('%s/odoo/action-spreadsheet_dashboard.ir_actions_dashboard_action' % url)
        page.wait_for_selector('.o_spreadsheet_dashboard_action', timeout=60000)
        for name, (module, file_name) in SAMPLES.items():
            page.click('.o_search_panel_section li:has-text("%s")' % name)
            page.wait_for_timeout(3000)
            data = page.evaluate(EXPORT_JS, name)
            path = os.path.join(ROOT, module, 'data', 'files', file_name)
            with open(path, 'w', encoding='utf-8') as file:
                json.dump(data, file, indent=4, ensure_ascii=False)
                file.write('\n')
            print('written', path)
        browser.close()


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
