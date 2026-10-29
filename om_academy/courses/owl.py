# Course: your first Owl components. A screen of your own in Odoo (a client
# action), its state, a component in it, data read from the server, and the
# services of the web client. JavaScript is files the browser loads, so this
# course is written in the learner's editor only: Code it.
from odoo.tools.translate import LazyTranslate

from ..models.course_files import ICON, ICON_PATH

_lt = LazyTranslate(__name__)

MANIFEST = """\
{
    'name': 'Owl Lab',
    'version': '1.0',
    'summary': 'My first Owl components',
    'depends': ['base', 'web'],
    'data': [
        'views/lab_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'learn_owl/static/src/**/*',
        ],
    },
    'application': True,
    'license': 'LGPL-3',
}
"""

VIEWS = """\
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="lab_action" model="ir.actions.client">
        <field name="name">Owl Lab</field>
        <field name="tag">learn_owl.lab</field>
    </record>

    <menuitem id="lab_root" name="Owl Lab" action="lab_action"
              web_icon="learn_owl,static/description/icon.png"/>

</odoo>
"""

JS_V1 = """\
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

export class Lab extends Component {
    static template = "learn_owl.Lab";

    props = useProps(standardActionServiceProps);
}

registry.category("actions").add("learn_owl.lab", Lab);
"""

XML_V1 = """\
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">

    <t t-name="learn_owl.Lab">
        <div class="o_learn_owl_lab p-4">
            <h1>Hello, Owl!</h1>
            <p>This screen is yours: a component, written in JavaScript.</p>
        </div>
    </t>

</templates>
"""

JS_V2 = """\
import { Component, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

export class Lab extends Component {
    static template = "learn_owl.Lab";

    props = useProps(standardActionServiceProps);

    setup() {
        this.state = proxy({ count: 0 });
    }

    increment() {
        this.state.count++;
    }
}

registry.category("actions").add("learn_owl.lab", Lab);
"""

XML_V2 = """\
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">

    <t t-name="learn_owl.Lab">
        <div class="o_learn_owl_lab p-4">
            <h1>Hello, Owl!</h1>
            <p>This screen is yours: a component, written in JavaScript.</p>
            <button class="btn btn-primary" t-on-click="() => this.increment()">Click me</button>
            <p class="mt-3">Clicked <b t-out="this.state.count"/> times.</p>
            <p t-if="this.state.count &gt;= 10">Ten clicks! You are getting the hang of it.</p>
        </div>
    </t>

</templates>
"""

CARD_JS = """\
import { Component, t, useProps } from "@odoo/owl";

export class Card extends Component {
    static template = "learn_owl.Card";

    props = useProps({
        title: t.string(),
        value: t.number(),
    });
}
"""

CARD_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">

    <t t-name="learn_owl.Card">
        <div class="d-inline-block border rounded p-3 me-3 mb-3 text-center">
            <div class="text-muted small" t-out="this.props.title"/>
            <div class="fs-1 fw-bold" t-out="this.props.value"/>
        </div>
    </t>

</templates>
"""

JS_V3 = """\
import { Component, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { Card } from "./card";

export class Lab extends Component {
    static template = "learn_owl.Lab";
    static components = { Card };

    props = useProps(standardActionServiceProps);

    setup() {
        this.state = proxy({ count: 0 });
    }

    increment() {
        this.state.count++;
    }
}

registry.category("actions").add("learn_owl.lab", Lab);
"""

XML_V3 = """\
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">

    <t t-name="learn_owl.Lab">
        <div class="o_learn_owl_lab p-4">
            <h1>Hello, Owl!</h1>
            <Card title="'Clicks'" value="this.state.count"/>
            <div>
                <button class="btn btn-primary" t-on-click="() => this.increment()">Click me</button>
            </div>
            <p t-if="this.state.count &gt;= 10" class="mt-3">Ten clicks! You are getting the hang of it.</p>
        </div>
    </t>

</templates>
"""

JS_V4 = """\
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { Card } from "./card";

export class Lab extends Component {
    static template = "learn_owl.Lab";
    static components = { Card };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ count: 0, total: 0, partners: [] });
        onWillStart(async () => {
            this.state.total = await this.orm.searchCount("res.partner", []);
            this.state.partners = await this.orm.searchRead("res.partner", [], ["name", "email"], {
                limit: 5,
                order: "id desc",
            });
        });
    }

    increment() {
        this.state.count++;
    }
}

registry.category("actions").add("learn_owl.lab", Lab);
"""

XML_V4 = """\
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">

    <t t-name="learn_owl.Lab">
        <div class="o_learn_owl_lab p-4">
            <h1>Hello, Owl!</h1>
            <Card title="'Clicks'" value="this.state.count"/>
            <Card title="'Contacts'" value="this.state.total"/>
            <div>
                <button class="btn btn-primary" t-on-click="() => this.increment()">Click me</button>
            </div>
            <h4 class="mt-4">The latest contacts</h4>
            <ul>
                <li t-foreach="this.state.partners" t-as="partner" t-key="partner.id">
                    <t t-out="partner.name"/> <span class="text-muted" t-out="partner.email or ''"/>
                </li>
            </ul>
        </div>
    </t>

</templates>
"""

JS_V5 = """\
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { Card } from "./card";

export class Lab extends Component {
    static template = "learn_owl.Lab";
    static components = { Card };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.state = proxy({ count: 0, total: 0, partners: [] });
        onWillStart(async () => {
            this.state.total = await this.orm.searchCount("res.partner", []);
            this.state.partners = await this.orm.searchRead("res.partner", [], ["name", "email"], {
                limit: 5,
                order: "id desc",
            });
        });
    }

    increment() {
        this.state.count++;
        if (this.state.count === 10) {
            this.notification.add("Ten clicks! You are getting the hang of it.", { type: "success" });
        }
    }

    openContacts() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Contacts",
            res_model: "res.partner",
            views: [[false, "list"], [false, "form"]],
        });
    }
}

registry.category("actions").add("learn_owl.lab", Lab);
"""

XML_V5 = """\
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">

    <t t-name="learn_owl.Lab">
        <div class="o_learn_owl_lab p-4">
            <h1>Hello, Owl!</h1>
            <Card title="'Clicks'" value="this.state.count"/>
            <Card title="'Contacts'" value="this.state.total"/>
            <div>
                <button class="btn btn-primary" t-on-click="() => this.increment()">Click me</button>
                <button class="btn btn-secondary ms-2" t-on-click="() => this.openContacts()">Open the contacts</button>
            </div>
            <h4 class="mt-4">The latest contacts</h4>
            <ul>
                <li t-foreach="this.state.partners" t-as="partner" t-key="partner.id">
                    <t t-out="partner.name"/> <span class="text-muted" t-out="partner.email or ''"/>
                </li>
            </ul>
        </div>
    </t>

</templates>
"""

LAB_JS = 'static/src/lab/lab.js'
LAB_XML = 'static/src/lab/lab.xml'
CARD_JS_PATH = 'static/src/lab/card.js'
CARD_XML_PATH = 'static/src/lab/card.xml'

RELOAD = _lt("JavaScript and its templates are assets: save, then <b>reload the page</b> (F5) and "
             "click <b>Check</b>. No restart, no upgrade.")


def files(path, *needles):
    return {'kind': 'files', 'path': path, 'needles': list(needles)}


COURSE = {
    'key': 'owl',
    'module': 'learn_owl',
    'app_name': 'Owl Lab',
    'main_model': 'res.partner',
    'main_action': 'lab_action',
    'modes': ['code'],
    'name': _lt("Your first Owl components"),
    'summary': _lt("JavaScript in Odoo: a screen of your own, its state, a component in it, data from the "
                   "server and the services of the web client, with Owl, Odoo's framework."),
    'minutes': 35,
    'level': _lt("Intermediate"),
    'video_url': False,
    'default_icon': 'bolt',
    'challenges': [
        {'key': 'reset', 'kind': 'code', 'path': LAB_JS, 'xml': LAB_XML,
         'needles': [r'reset\s*\(\s*\)\s*\{', r'this\.state\.count\s*=\s*0'], 'xml_needles': [r'this\.reset\s*\('],
         'title': _lt("A Reset button"),
         'todo': _lt("Add a button Reset next to Click me: it puts the clicks back to 0."),
         'hint_code': _lt("A method reset() in the component that sets this.state.count to 0, and a button "
                          "in the template whose t-on-click calls it. Reload the page."),
         'hint_live': _lt("A method reset() in the component that sets this.state.count to 0, and a button "
                          "in the template whose t-on-click calls it. Reload the page.")},
        {'key': 'ten', 'kind': 'code', 'path': LAB_JS, 'needles': [r'limit\s*:\s*10\b'],
         'title': _lt("Ten contacts"),
         'todo': _lt("Show the 10 latest contacts instead of 5."),
         'hint_code': _lt("The limit given to searchRead. Reload the page."),
         'hint_live': _lt("The limit given to searchRead. Reload the page.")},
    ],
    'steps': [
        {
            'key': 'intro',
            'title': _lt("What we will build"),
            'intro': True,
            'explain': _lt(
                "<p>The screens of Odoo, forms, lists, Discuss, this Academy, are <b>components</b> written "
                "in JavaScript with <b>Owl</b>, Odoo's own framework. In this course you write yours: "
                "<b>Owl Lab</b>, a screen with a button that counts, cards, and the latest contacts read "
                "from the server.</p>"
                "<p>JavaScript is files the browser loads, so this course is written in your editor, in "
                "<b>Code it</b>. You know modules already: the first course is the place to start.</p>"),
        },
        {
            'key': 'skeleton',
            'title': _lt("A screen of your own"),
            'explain': _lt(
                "<p>A screen of Odoo that is not a form nor a list is a <b>client action</b>: an action "
                "with a <i>tag</i>, and a component registered under that tag. The menu opens the action, "
                "the web client finds the component and shows it.</p>"
                "<dl><dt>Component</dt><dd>a class of JavaScript, and the template it renders.</dd>"
                "<dt>Template</dt><dd>its HTML, in an XML file, with directives like the QWeb of "
                "reports.</dd>"
                "<dt>Assets</dt><dd>the JavaScript, CSS and templates the browser loads, listed in the "
                "manifest.</dd></dl>"
                "<ul><li>the manifest lists the files of <code>static/src</code> in the assets of the "
                "backend, <code>web.assets_backend</code>;</li>"
                "<li><code>ir.actions.client</code> with the tag <code>learn_owl.lab</code>, and a menu "
                "that opens it;</li>"
                "<li><code>registry.category(\"actions\").add()</code> registers the component under the "
                "same tag;</li>"
                "<li><code>static template</code> names its template, the one with that "
                "<code>t-name</code>;</li>"
                "<li><code>props = useProps(...)</code> declares what the web client gives a client "
                "action: the action itself, mainly.</li></ul>"),
            'files': {
                '__manifest__.py': MANIFEST,
                '__init__.py': '',
                'views/lab_views.xml': VIEWS,
                LAB_JS: JS_V1,
                LAB_XML: XML_V1,
                ICON_PATH: ICON,
            },
            'checks': [files(LAB_JS, 'registry.category("actions").add("learn_owl.lab"', 'static template = "learn_owl.Lab"'),
                       files(LAB_XML, 't-name="learn_owl.Lab"'),
                       {'kind': 'assets', 'bundle': 'web.assets_backend'}],
            'code_note': _lt("Create <code>learn_owl</code> in your addons path, or click <b>Write it for "
                             "me</b>, then <b>Install</b>."),
            'see': 'app',
            'see_text': _lt("Owl Lab is on the home screen: open it, and say hello."),
        },
        {
            'key': 'state',
            'title': _lt("React to a click"),
            'explain': _lt(
                "<p>A component has a <b>state</b>: the values its template shows. Change the state, and "
                "Owl draws the screen again, by itself.</p>"
                "<dl><dt>proxy</dt><dd>makes an object reactive: when a value of it changes, the "
                "components that show it render again.</dd>"
                "<dt>setup()</dt><dd>runs once, when the component is created: the place to prepare its "
                "state.</dd></dl>"
                "<ul><li><code>this.state = proxy({ count: 0 })</code>: the clicks, at 0;</li>"
                "<li><code>t-on-click</code> calls <code>increment()</code> at each click;</li>"
                "<li><code>t-out</code> prints a value, and <code>t-if</code> shows an element only "
                "when its condition is true.</li></ul>"),
            'files': {LAB_JS: JS_V2, LAB_XML: XML_V2},
            'checks': [files(LAB_JS, 'proxy(', 'increment()'), files(LAB_XML, 't-on-click', 'this.state.count')],
            'code_note': RELOAD,
            'see': 'app',
            'see_text': _lt("Click the button: the number follows."),
        },
        {
            'key': 'child',
            'title': _lt("A component in a component"),
            'explain': _lt(
                "<p>Screens are made of small components put together: a card here, a button there. "
                "Here, <b>Card</b>: a title and a number, shown by the Lab.</p>"
                "<dl><dt>Props</dt><dd>what a component receives from the one that shows it: here a "
                "title and a value.</dd></dl>"
                "<ul><li><code>useProps({ title: t.string(), value: t.number() })</code> declares the "
                "props of Card, and their types: Owl checks them in developer mode;</li>"
                "<li><code>static components = { Card }</code> lets the template of the Lab use it;</li>"
                "<li><code>&lt;Card title=\"'Clicks'\" value=\"this.state.count\"/&gt;</code>: each prop "
                "is a JavaScript expression, so text goes in quotes;</li>"
                "<li>the count changes, Card gets the new value and draws it again.</li></ul>"),
            'files': {CARD_JS_PATH: CARD_JS, 'static/src/lab/card.xml': CARD_XML, LAB_JS: JS_V3, LAB_XML: XML_V3},
            'checks': [files(CARD_JS_PATH, 'useProps(', 'static template = "learn_owl.Card"'),
                       files(LAB_JS, 'static components = { Card }'), files(LAB_XML, '<Card ')],
            'code_note': RELOAD,
            'see': 'app',
            'see_text': _lt("A card shows the clicks: click, and watch it."),
        },
        {
            'key': 'orm',
            'title': _lt("Data from the server"),
            'explain': _lt(
                "<p>The records are on the server: the component asks for them with the <b>ORM</b> "
                "service, the same methods as in Python, called over the network.</p>"
                "<dl><dt>Service</dt><dd>a tool the web client gives every component: the ORM, the "
                "notifications, the actions...</dd>"
                "<dt>onWillStart</dt><dd>runs before the first render, and waits for what it returns: "
                "the data arrives before the screen is shown.</dd></dl>"
                "<ul><li><code>useService(\"orm\")</code> gets the ORM;</li>"
                "<li><code>searchCount</code> counts the contacts, <code>searchRead</code> reads 5 of "
                "them, their name and email, the latest first;</li>"
                "<li><code>t-foreach</code> repeats the <code>li</code> for each contact, "
                "<code>t-key</code> tells Owl which is which.</li></ul>"),
            'files': {LAB_JS: JS_V4, LAB_XML: XML_V4},
            'checks': [files(LAB_JS, 'useService("orm")', 'searchRead(', 'onWillStart('),
                       files(LAB_XML, 't-foreach')],
            'code_note': RELOAD,
            'see': 'app',
            'see_text': _lt("The number of contacts, and the latest five."),
        },
        {
            'key': 'services',
            'title': _lt("Tell the user, open a view"),
            'explain': _lt(
                "<p>Two more services, used everywhere in Odoo: <b>notification</b> shows a message in "
                "the corner, <b>action</b> opens an action, as a menu does.</p>"
                "<ul><li>at ten clicks, <code>this.notification.add()</code> cheers, in green with "
                "<code>type: \"success\"</code>;</li>"
                "<li><code>this.action.doAction({...})</code> opens the contacts, in a list then a form: "
                "the same dictionary as an action returned by Python;</li>"
                "<li>the Back of the browser, and the breadcrumbs, come back to your Lab.</li></ul>"),
            'files': {LAB_JS: JS_V5, LAB_XML: XML_V5},
            'checks': [files(LAB_JS, 'useService("notification")', 'useService("action")', 'doAction('),
                       files(LAB_XML, 'this.openContacts()')],
            'code_note': RELOAD,
            'see': 'app',
            'see_text': _lt("Click ten times, then open the contacts."),
        },
        {
            'key': 'finish',
            'title': _lt("Your Owl Lab is ready"),
            'finish': True,
            'explain': _lt(
                "<p>A client action, a component and its state, a child component with props, data read "
                "with the ORM, a notification and an action: the pieces of every screen of Odoo.</p>"
                "<p>Next, read the components of Odoo itself, in <code>addons/web/static/src</code>: you "
                "will recognize them. <b>Export as app</b> gives you the module as a zip.</p>"),
            'files': {},
            'see': 'app',
            'see_text': _lt("Your Owl Lab."),
        },
    ],
}
