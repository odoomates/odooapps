from odoo import SUPERUSER_ID, api
from odoo.tests import TransactionCase, tagged

from odoo.addons.flow_visualizer.models import simulation


@tagged('post_install', '-at_install')
class TestSimulationEngine(TransactionCase):
    """ The engine on a connection of its own, as a request would use it:
    steps, going back to one, and leaving nothing behind once discarded. """

    def setUp(self):
        super().setUp()
        self.simulation = simulation.Simulation(self.env.cr.dbname, self.env.uid)
        self.addCleanup(self._discard)

    def _discard(self):
        if not self.simulation.ended:
            self.simulation.ask('discard')

    def run_in(self, function):
        """ What one request does: its cursor is one of the simulation. """
        with self.simulation.cursor() as cr:
            return function(api.Environment(cr, SUPERUSER_ID, {}))

    def committed(self, ids):
        with simulation.real_cursor(self.env.cr.dbname) as cr:
            cr.execute("SELECT count(*) FROM res_partner WHERE id IN %s", [tuple(ids)])
            return cr.fetchone()[0]

    def step(self, res_id):
        self.simulation.ask('step', trace_id=0, name='res.partner.create', model='res.partner', res_id=res_id)

    def test_going_back_to_a_step(self):
        first = self.run_in(lambda env: env['res.partner'].create({'name': 'Simulated First'}).id)
        self.step(first)
        second = self.run_in(lambda env: env['res.partner'].create({'name': 'Simulated Second'}).id)
        self.step(second)
        self.assertEqual(self.committed([first, second]), 0, "nothing is saved during a simulation")
        self.assertEqual(self.run_in(lambda env: len(env['res.partner'].browse([first, second]).exists())), 2)

        self.simulation.ask('rewind', step_id=1)
        self.assertTrue(self.run_in(lambda env: env['res.partner'].browse(first).exists().id))
        self.assertFalse(self.run_in(lambda env: env['res.partner'].browse(second).exists().id))
        self.assertEqual([step['abandoned'] for step in self.simulation.steps], [False, True])

        # a new branch from there
        third = self.run_in(lambda env: env['res.partner'].create({'name': 'Simulated Third'}).id)
        self.step(third)
        self.assertEqual([step['abandoned'] for step in self.simulation.state()['steps']], [False, True, False])

        self.simulation.ask('discard')
        self.assertTrue(self.simulation.ended)
        self.assertEqual(self.committed([first, third]), 0)

    def test_back_to_the_start(self):
        partner = self.run_in(lambda env: env['res.partner'].create({'name': 'Simulated'}).id)
        self.step(partner)
        self.simulation.ask('rewind', step_id=0)
        self.assertFalse(self.run_in(lambda env: env['res.partner'].browse(partner).exists().id))

    def test_a_failed_request_leaves_the_step_intact(self):
        partner = self.run_in(lambda env: env['res.partner'].create({'name': 'Kept'}).id)
        self.step(partner)
        with self.assertRaises(ZeroDivisionError):
            self.run_in(lambda env: (env['res.partner'].browse(partner).write({'name': 'Changed'}), 1 / 0))
        self.assertEqual(self.run_in(lambda env: env['res.partner'].browse(partner).name), 'Kept')

    def test_each_request_has_its_own_time(self):
        first = self.run_in(lambda env: env.cr.now())
        second = self.run_in(lambda env: env.cr.now())
        self.assertLess(first, second, "one transaction, but the clock moves")
