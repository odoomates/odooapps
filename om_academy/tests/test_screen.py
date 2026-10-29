# The Academy screen in a browser: a course opened, built live step by step,
# and its code shown.
from odoo.tests import HttpCase, tagged

from odoo.addons.om_academy.tests.common import modules_on_disk, named_learner


@tagged('post_install', '-at_install')
class TestScreen(HttpCase):

    def setUp(self):
        super().setUp()
        modules_on_disk(self)
        named_learner(self)
        # what the browser built live is undone before the test's rollback: the
        # models built live are in the registry, which a rollback does not reset
        self.addCleanup(lambda: self.env['academy.progress'].search([])._reset())
        self.env.ref('base.user_admin').academy_welcomed = True

    def test_the_welcome_guide(self):
        admin = self.env.ref('base.user_admin')
        admin.academy_welcomed = False
        code = """(async () => {
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const until = async (selector) => {
                for (let tries = 0; tries < 75; tries++) {
                    const element = document.querySelector(selector);
                    if (element) {
                        return element;
                    }
                    await wait(200);
                }
                throw new Error('not found: ' + selector);
            };
            const seeAll = async () => {
                for (const tab of document.querySelectorAll('.o_academy_tab')) {
                    tab.click();
                    await wait(50);
                }
            };
            for (const screen of ['welcome', 'ways', 'path']) {
                await until(`.o_academy_welcome[data-screen="${screen}"]`);
                (await until('.o_academy_welcome_next')).click();
            }
            await until('.o_academy_welcome[data-screen="us"]');
            (await until('.o_academy_welcome_start')).click();
            await wait(500);
            if (document.querySelector('.o_academy_welcome')) {
                throw new Error('the guide is still open');
            }
            await until('.o_academy_card');
            console.log('test successful');
        })()"""
        self.browser_js('/odoo/action-om_academy.academy_action', code, login='admin', timeout=120)
        self.assertTrue(admin.academy_welcomed, "the guide opens on its own once")

    def test_build_live_from_the_screen(self):
        # a new learner: nothing built, no course started
        progresses = self.env['academy.progress'].search([])
        progresses._reset()
        progresses.unlink()
        code = """(async () => {
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const until = async (selector) => {
                for (let tries = 0; tries < 75; tries++) {
                    const element = document.querySelector(selector);
                    if (element) {
                        return element;
                    }
                    await wait(200);
                }
                throw new Error('not found: ' + selector);
            };
            const seeAll = async () => {
                for (const tab of document.querySelectorAll('.o_academy_tab')) {
                    tab.click();
                    await wait(50);
                }
            };
            const buildStep = async (key) => {
                // one step at a time: open it, read its files, build it
                (await until(`.o_academy_step_item[data-step="${key}"]:not(.locked)`)).click();
                await until(`.o_academy_step_item.active[data-step="${key}"]`);
                await wait(300);
                await seeAll();
                (await until('.o_academy_build')).click();
                await until(`.o_academy_step_item.done[data-step="${key}"]`);
            };
            (await until('.o_academy_card[data-course="library"]')).click();
            // the intro opens on the app to build: Next shows the choices
            await until('.o_academy_intro_preview img');
            (await until('.o_academy_next')).click();
            (await until('.o_academy_mode_card')).click();
            await wait(500);
            // the steps after the first one not built are locked
            (await until('.o_academy_step_item.locked[data-step="model"]')).click();
            await wait(300);
            if (document.querySelector('.o_academy_step_item.active[data-step="model"]')) {
                throw new Error('a step was opened before the ones before it were built');
            }
            await buildStep('skeleton');
            // the files of a step, each opened before building it; Next waits for the build
            (await until('.o_academy_next')).click();
            await until('.o_academy_step_item.active[data-step="model"]');
            await wait(300);
            if (!document.querySelector('.o_academy_next').disabled) {
                throw new Error('Next is enabled before the step is built');
            }
            (await until('.o_academy_build')).click();
            await wait(300);
            const active = document.querySelector('.o_academy_tab.active');
            if (document.querySelector('.o_academy_step_item.done[data-step="model"]') || active.textContent.trim() !== 'learn_library/__init__.py') {
                throw new Error('Build went on, or opened a file itself: the learner opens them');
            }
            if (document.querySelectorAll('.o_academy_tab.unseen').length !== 2) {
                throw new Error('the files not opened yet are not marked');
            }
            await buildStep('model');
            await buildStep('access');
            await buildStep('menu');
            await until('.o_academy_note');
            if (!document.querySelector('.o_academy_line.new')) {
                throw new Error('the new lines are not marked');
            }
            if (document.querySelectorAll('.o_academy_step_item.done').length !== 4) {
                throw new Error('the steps before were not built');
            }
            // See it in Odoo: a new tab, at the address of the app
            let opened = null;
            window.open = (url, target) => { opened = [url, target]; };
            (await until('.o_academy_see')).click();
            await wait(1000);
            if (!opened || !/^\/odoo\/action-\d+$/.test(opened[0]) || opened[1] !== '_blank') {
                throw new Error('See it did not open the app in a new tab: ' + JSON.stringify(opened));
            }
            console.log('test successful');
        })()"""
        self.browser_js('/odoo/action-om_academy.academy_action', code, login='admin', timeout=120)
        progress = self.env['academy.progress'].search([('user_id', '=', self.env.ref('base.user_admin').id)])
        self.assertEqual(progress.built, ['skeleton', 'model', 'access', 'menu'])

    def test_see_it_after_a_step_changed_the_views(self):
        """ A form seen, then a step removing one of its fields: the form opens
        again without the browser asking for the field that is gone. """
        progresses = self.env['academy.progress'].search([])
        progresses._reset()
        progresses.unlink()
        code = """(async () => {
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const until = async (selector) => {
                for (let tries = 0; tries < 75; tries++) {
                    const element = document.querySelector(selector);
                    if (element) {
                        return element;
                    }
                    await wait(200);
                }
                throw new Error('not found: ' + selector);
            };
            const seeAll = async () => {
                for (const tab of document.querySelectorAll('.o_academy_tab')) {
                    tab.click();
                    await wait(50);
                }
            };
            const buildStep = async (key) => {
                // one step at a time: open it, read its files, build it
                (await until(`.o_academy_step_item[data-step="${key}"]:not(.locked)`)).click();
                await until(`.o_academy_step_item.active[data-step="${key}"]`);
                await wait(300);
                await seeAll();
                (await until('.o_academy_build')).click();
                await until(`.o_academy_step_item.done[data-step="${key}"]`);
            };
            const academy = async () => {
                // back to the Academy, as a user does: the breadcrumb
                (await until('.o_breadcrumb .breadcrumb-item a, .o_breadcrumb a')).click();
                // the Academy opens on its courses: the learner opens theirs again
                (await until('.o_academy_card[data-course="library"]')).click();
                await until('.o_academy_step_item');
            };
            (await until('.o_academy_card[data-course="library"]')).click();
            // the intro opens on the app to build: Next shows the choices
            await until('.o_academy_intro_preview img');
            (await until('.o_academy_next')).click();
            (await until('.o_academy_mode_card')).click();
            await wait(500);
            for (const key of ['skeleton', 'model', 'access', 'menu']) {
                await buildStep(key);
            }
            (await until('.o_academy_step_item[data-step="form"]')).click();
            await until('.o_academy_step_item.active[data-step="form"]');
            if (document.querySelector('.o_academy_see')) {
                throw new Error('See it is shown before the step is built');
            }
            await wait(1000);  // the step clicked is shown
            await until('.o_academy_build');
            await seeAll();
            (await until('.o_academy_build')).click();
            await until('.o_academy_see');
            console.log('test successful');
        })()"""
        self.browser_js('/odoo/action-om_academy.academy_action', code, login='admin', timeout=180)
        Progress = self.env['academy.progress'].with_user(self.env.ref('base.user_admin'))
        index = {step['key']: step['index'] for step in Progress.academy_open('library')['steps']}
        # the learner's other tab: the form of a book
        self.env['x_library_book'].create({'x_name': 'Dune'})
        until_form = """(async () => {
            for (let tries = 0; tries < 75; tries++) {
                if (document.querySelector('%s')) {
                    console.log('test successful');
                    return;
                }
                await new Promise((resolve) => setTimeout(resolve, 200));
            }
            throw new Error('the form is not shown');
        })()"""
        self.browser_js(Progress.academy_see_url('library', index['form']), until_form % '.o_form_view', login='admin')
        # in the Academy, the next step changes the form: the other tab shows the new one
        code = """(async () => {
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const until = async (selector) => {
                for (let tries = 0; tries < 75; tries++) {
                    const element = document.querySelector(selector);
                    if (element) {
                        return element;
                    }
                    await wait(200);
                }
                throw new Error('not found: ' + selector);
            };
            const seeAll = async () => {
                for (const tab of document.querySelectorAll('.o_academy_tab')) {
                    tab.click();
                    await wait(50);
                }
            };
            const buildStep = async (key) => {
                // one step at a time: open it, read its files, build it
                (await until(`.o_academy_step_item[data-step="${key}"]:not(.locked)`)).click();
                await until(`.o_academy_step_item.active[data-step="${key}"]`);
                await wait(300);
                await seeAll();
                (await until('.o_academy_build')).click();
                await until(`.o_academy_step_item.done[data-step="${key}"]`);
            };
            (await until('.o_academy_card[data-course="library"]')).click();
            await buildStep('list_search');
            await buildStep('authors');
            await until('.o_academy_see');
            console.log('test successful');
        })()"""
        self.browser_js('/odoo/action-om_academy.academy_action', code, login='admin', timeout=180)
        self.browser_js(Progress.academy_see_url('library', index['authors']),
                        until_form % '.o_form_view .o_field_widget[name="x_author_id"]', login='admin')
