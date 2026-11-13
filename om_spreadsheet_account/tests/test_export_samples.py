import importlib.util
import json
import os

from odoo.tests import HttpCase, tagged

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _export_script():
    spec = importlib.util.spec_from_file_location(
        'om_spreadsheet_export_samples', os.path.join(ROOT, 'om_spreadsheet_account', 'tools', 'export_samples.py'))
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


@tagged('-standard', '-at_install', 'post_install', 'om_export_samples')
class ExportSamples(HttpCase):
    """ Not a test: writes the sample dashboards, with the browser of the tests, from the database it runs on (one
    with demo data). Run it with --test-tags om_export_samples. """

    def test_export_samples(self):
        script = _export_script()
        installed = set(self.env['ir.module.module'].search([('state', '=', 'installed')]).mapped('name'))
        samples = {name: target for name, target in script.SAMPLES.items() if target[0] in installed}
        # the browser hands the samples back through a parameter, read below in the same transaction
        code = """
            (async () => {
                const exportSample = %(export)s;
                const orm = odoo.__WOWL_DEBUG__.root.env.services.orm;
                for (const name of %(names)s) {
                    const data = await exportSample(name);
                    await orm.call("ir.config_parameter", "set_param", ["om_spreadsheet_sample." + name, JSON.stringify(data)]);
                }
                console.log("test successful");
            })();
        """ % {'export': script.EXPORT_JS, 'names': json.dumps(list(samples))}
        self.browser_js(
            '/odoo/action-spreadsheet_dashboard.ir_actions_dashboard_action', code,
            ready="!!(odoo.__WOWL_DEBUG__ && document.querySelector('.o_spreadsheet_dashboard_action'))",
            login='admin', timeout=600,
        )
        for name, (module, file_name) in samples.items():
            data = json.loads(self.env['ir.config_parameter'].get_param('om_spreadsheet_sample.' + name))
            path = os.path.join(ROOT, module, 'data', 'files', file_name)
            with open(path, 'w', encoding='utf-8') as file:
                json.dump(data, file, indent=4, ensure_ascii=False)
                file.write('\n')
