import inspect
from unittest.mock import patch

from odoo.addons.base.models import res_partner
from odoo.tests import TransactionCase, tagged

from odoo.addons.flow_visualizer.models import code_link


@tagged('post_install', '-at_install')
class TestCodeLink(TransactionCase):

    def setUp(self):
        super().setUp()
        self.path = inspect.getsourcefile(res_partner)
        self.line = inspect.getsourcelines(res_partner.ResPartner.name_create)[1]

    def test_a_remote_viewer_gets_the_repository_page(self):
        result = code_link.open_code(self.path, self.line, '10.1.2.3')
        if 'error' in result:
            self.skipTest("Odoo is not a git checkout here")
        self.assertRegex(result['url'], r'^https://github\.com/odoo/odoo/blob/[0-9a-f]{40}/odoo/addons/base/models/res_partner\.py#L\d+$')

    def test_a_local_viewer_gets_the_editor(self):
        editor = code_link.find_editor()
        if not editor:
            self.skipTest("no editor installed here")
        with patch.object(code_link.subprocess, 'Popen') as popen:
            result = code_link.open_code(self.path, self.line, '127.0.0.1')
        self.assertEqual(result, {'opened': editor[0]})
        command = popen.call_args.args[0]
        self.assertEqual(command[0], editor[1])
        self.assertIn(self.path, ' '.join(command))

    def test_only_source_files_open(self):
        with patch.object(code_link.subprocess, 'Popen') as popen:
            self.assertEqual(code_link.open_code('/etc/passwd', 1, '127.0.0.1'), {'error': 'not_source'})
            self.assertEqual(code_link.open_code(self.path + '.txt', 1, '127.0.0.1'), {'error': 'not_source'})
        popen.assert_not_called()

    def test_short_path(self):
        self.assertEqual(code_link.short_path(self.path), 'base/models/res_partner.py')
