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
    const { helpers } = odoo.loader.modules.get("@odoo/o-spreadsheet");
    const loader = odoo.__WOWL_DEBUG__.root.env.services.spreadsheet_dashboard_loader;
    await loader.load();
    const found = {};
    for (const group of loader.getDashboardGroups()) {
        for (const dashboard of group.dashboards) {
            found[dashboard.data.name] = dashboard.data.id;
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
            for (const sheetId of model.getters.getSheetIds()) {
                const sheetName = model.getters.getSheetName(sheetId);
                for (let row = 0; row < model.getters.getNumberRows(sheetId); row++) {
                    for (let col = 0; col < model.getters.getNumberCols(sheetId); col++) {
                        const cell = model.getters.getEvaluatedCell({ sheetId, col, row });
                        if (cell.type !== "error") {
                            continue;
                        }
                        const message = String(cell.message || cell.value);
                        if (message.includes("Loading")) {
                            loading = true;
                        } else {
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
            const cell = model.getters.getEvaluatedCell({ sheetId, ...helpers.toCartesian(xc) });
            if (typeof value === "number" ? Math.abs((cell.value || 0) - value) > 0.01 : cell.value !== value) {
                failures.push(`${name}: ${reference} is ${cell.value}, expected ${value}`);
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
        '/odoo/action-spreadsheet_dashboard.ir_actions_dashboard_action',
        CHECK_DASHBOARDS_JS % {'names': json.dumps(names), 'expected': json.dumps(expected or {})},
        ready="!!(odoo.__WOWL_DEBUG__ && document.querySelector('.o_spreadsheet_dashboard_action'))",
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
    return {name: build().to_json() for name, build in script.DASHBOARDS.items()}


def shipped_dashboard(module, file_name):
    with file_open('%s/data/files/%s' % (module, file_name)) as file:
        return json.load(file)


def check_sample(case, xmlid):
    """ The sample of the dashboard shows values only: no formula, no data source """
    dashboard = case.env.ref(xmlid)
    sample = dashboard._get_sample_dashboard()
    case.assertTrue(sample, 'the sample file of %s exists' % dashboard.name)
    case.assertFalse(sample['pivots'] or sample['lists'] or sample['globalFilters'])
    cells = [value for sheet in sample['sheets'] for value in sheet['cells'].values()]
    case.assertTrue(cells)
    case.assertFalse([value for value in cells if isinstance(value, str) and value.startswith('=')])
    for sheet in sample['sheets']:
        for figure in sheet['figures']:
            for definition in figure['data'].get('chartDefinitions', {}).values():
                case.assertNotEqual(definition['dataSource']['type'], 'odoo')
    # a database without the records of these models shows the sample
    case.assertTrue(dashboard.main_data_model_ids)
