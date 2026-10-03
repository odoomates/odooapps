import importlib.util
import json
import os

from odoo.tools import file_open

# Opens the dashboards in the browser, waits for their data and fails on the cells in error; `expected` gives the
# value of some cells, e.g. {"Accounting Overview": {"Data!B6": 1000}}.
CHECK_DASHBOARDS_JS = """
(async () => {
    const names = %(names)s;
    const expected = %(expected)s;
    // Odoo 16: the modules of the lazy bundle of the spreadsheets, loaded by the dashboard action
    const modules = odoo.__DEBUG__.services;
    const { helpers } = window.o_spreadsheet;
    const { DashboardLoader } = modules["@spreadsheet_dashboard/bundle/dashboard_action/dashboard_loader"];
    const env = odoo.__WOWL_DEBUG__.root.env;
    const orm = env.services.orm;
    const loader = new DashboardLoader(env, orm, async (dashboardId) => {
        const [record] = await orm.read("spreadsheet.dashboard", [dashboardId], ["raw"]);
        return { data: record.raw, revisions: [] };
    });
    await loader.load();
    const found = {};
    for (const group of loader.getDashboardGroups()) {
        for (const dashboard of group.dashboards) {
            found[dashboard.displayName] = dashboard.id;
        }
    }
    const failures = [];
    for (const name of names) {
        if (!found[name]) {
            failures.push(`${name}: not in the dashboards (${Object.keys(found)})`);
            continue;
        }
        const dashboard = loader.getDashboard(found[name]);
        await dashboard.promise;
        const model = dashboard.model;
        let errors = [];
        for (let attempt = 0; attempt < 150; attempt++) {
            errors = [];
            let loading = false;
            model.dispatch("EVALUATE_CELLS");
            for (const sheetId of model.getters.getSheetIds()) {
                const sheetName = model.getters.getSheetName(sheetId);
                for (let row = 0; row < model.getters.getNumberRows(sheetId); row++) {
                    for (let col = 0; col < model.getters.getNumberCols(sheetId); col++) {
                        const cell = model.getters.getCell(sheetId, col, row);
                        if (!cell) {
                            continue;
                        }
                        const evaluated = cell.evaluated;
                        if (evaluated.value === "Loading...") {
                            loading = true;
                        } else if (evaluated.type === "error") {
                            const message = String((evaluated.error && evaluated.error.message) || evaluated.value);
                            errors.push(`${sheetName}!${helpers.toXC(col, row)}: ${message}`);
                        }
                    }
                }
            }
            if (!loading) {
                break;
            }
            await new Promise((resolve) => setTimeout(resolve, 200));
        }
        for (const error of errors) {
            failures.push(`${name}: ${error}`);
        }
        for (const [reference, value] of Object.entries(expected[name] || {})) {
            const [sheetName, xc] = reference.split("!");
            const sheetId = model.getters.getSheetIdByName(sheetName);
            const { col, row } = helpers.toCartesian(xc);
            const cell = model.getters.getCell(sheetId, col, row);
            const actual = cell ? cell.evaluated.value : undefined;
            if (typeof value === "number" ? Math.abs((actual || 0) - value) > 0.01 : actual !== value) {
                failures.push(`${name}: ${reference} is ${actual}, expected ${value}`);
            }
        }
    }
    if (failures.length) {
        console.error("Dashboard errors:\\n" + failures.join("\\n"));
    } else {
        console.log("test successful");
    }
})();
"""


def check_dashboards(case, names, expected=None):
    """ Open the dashboards in the browser as the admin and check their cells """
    case.browser_js(
        '/web#action=spreadsheet_dashboard.ir_actions_dashboard_action',
        CHECK_DASHBOARDS_JS % {'names': json.dumps(names), 'expected': json.dumps(expected or {})},
        ready="!!(odoo.__WOWL_DEBUG__ && document.querySelector('.o_spreadsheet_dashboard_action')"
              " && odoo.__DEBUG__.services['@spreadsheet_dashboard/bundle/dashboard_action/dashboard_loader'])",
        login='admin',
        timeout=180,
    )


def built_dashboards(module):
    """ :return: {file name: JSON} as the build script of the module writes them today """
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        module, 'tools', 'build_dashboards.py')
    spec = importlib.util.spec_from_file_location('%s_build_dashboards' % module, path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return {name: build().to_odoo_16_json() for name, build in script.DASHBOARDS.items()}


def shipped_dashboard(module, file_name):
    with file_open('%s/data/files/%s' % (module, file_name)) as file:
        return json.load(file)
