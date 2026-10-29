# Course 1: build your first app, on the subject the learner picks (a library,
# a car rental, a hotel, tool lending): the same steps, the subject's words. Each
# step gives the files of the learner's module as they are after the step (only
# the files the step changes), and the Python part of the step for Build it
# live: the views, actions, menus and access rights are read from the XML and
# CSV files themselves. {{token}}s are the words of the subject (THEMES).
import re

from odoo.http import request
from odoo.tools.translate import LazyTranslate

from ..models.course_files import ICON, ICON_PATH

_lt = LazyTranslate(__name__)

MANIFEST = """\
{
    'name': '{{App}}',
    'version': '1.0',
    'summary': 'My first Odoo app',
    'depends': [%s],
    'data': [%s],
    'application': True,
    'license': 'LGPL-3',
}
"""


def manifest(*data, depends=('base',)):
    return MANIFEST % (', '.join(map(repr, depends)),
                       ''.join('\n        %r,' % path for path in data) + ('\n    ' if data else ''))


BOOK_V1 = """\
from odoo import fields, models


class {{Cls}}{{Item}}(models.Model):
    _name = '{{p}}.{{item}}'
    _description = '{{Item}}'

    name = fields.Char(string='{{Name}}', required=True)
    {{maker}} = fields.Char()
    {{date1}} = fields.Date(string='{{Date1}}')
"""

BOOK_V2 = """\
from odoo import fields, models


class {{Cls}}{{Item}}(models.Model):
    _name = '{{p}}.{{item}}'
    _description = '{{Item}}'

    name = fields.Char(string='{{Name}}', required=True)
    {{maker}}_id = fields.Many2one('{{p}}.{{maker}}', string='{{Maker}}')
    {{date1}} = fields.Date(string='{{Date1}}')
"""

BOOK_V3 = """\
from odoo import fields, models


class {{Cls}}{{Item}}(models.Model):
    _name = '{{p}}.{{item}}'
    _description = '{{Item}}'

    name = fields.Char(string='{{Name}}', required=True)
    {{maker}}_id = fields.Many2one('{{p}}.{{maker}}', string='{{Maker}}')
    {{date1}} = fields.Date(string='{{Date1}}')
    state = fields.Selection(
        [('available', 'Available'), ('{{taken}}', '{{Taken}}')],
        string='Status', default='available', required=True)

    def {{take}}(self):
        self.write({'state': '{{taken}}'})

    def {{give}}(self):
        self.write({'state': 'available'})
"""

BOOK_V4 = """\
from odoo import api, fields, models


class {{Cls}}{{Item}}(models.Model):
    _name = '{{p}}.{{item}}'
    _description = '{{Item}}'

    name = fields.Char(string='{{Name}}', required=True)
    {{maker}}_id = fields.Many2one('{{p}}.{{maker}}', string='{{Maker}}')
    {{date1}} = fields.Date(string='{{Date1}}')
    state = fields.Selection(
        [('available', 'Available'), ('{{taken}}', '{{Taken}}')],
        string='Status', default='available', required=True)
    {{date2}} = fields.Date(string='{{Date2}}')
    {{days}} = fields.Integer(compute='_compute_{{days}}')

    @api.depends('{{date2}}', 'state')
    def _compute_{{days}}(self):
        today = fields.Date.context_today(self)
        for {{item}} in self:
            if {{item}}.state == '{{taken}}' and {{item}}.{{date2}}:
                {{item}}.{{days}} = (today - {{item}}.{{date2}}).days
            else:
                {{item}}.{{days}} = 0

    def {{take}}(self):
        self.write({'state': '{{taken}}', '{{date2}}': fields.Date.context_today(self)})

    def {{give}}(self):
        self.write({'state': 'available', '{{date2}}': False})
"""

# the extra steps: a chatter, then tracked fields
BOOK_V5 = BOOK_V4.replace("""    _description = '{{Item}}'
""", """    _description = '{{Item}}'
    _inherit = ['mail.thread']
""")

BOOK_V6 = (BOOK_V5
           .replace("{{maker}}_id = fields.Many2one('{{p}}.{{maker}}', string='{{Maker}}')",
                    "{{maker}}_id = fields.Many2one('{{p}}.{{maker}}', string='{{Maker}}', tracking=True)")
           .replace("string='Status', default='available', required=True)",
                    "string='Status', default='available', required=True, tracking=True)"))

AUTHOR = """\
from odoo import fields, models


class {{Cls}}{{Maker}}(models.Model):
    _name = '{{p}}.{{maker}}'
    _description = '{{Maker}}'

    name = fields.Char(required=True)
"""

ACCESS_V1 = """\
id,name,model_id,group_id/id,operation,domain
access_{{p}}_{{item}}_user,{{p}}.{{item}} user,{{p}}.{{item}},base.group_user,crud,
"""

ACCESS_V2 = ACCESS_V1 + """\
access_{{p}}_{{maker}}_user,{{p}}.{{maker}} user,{{p}}.{{maker}},base.group_user,crud,
"""

MENUS_V1 = """\
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="{{p}}_{{item}}_action" model="ir.actions.act_window">
        <field name="name">{{Items}}</field>
        <field name="res_model">{{p}}.{{item}}</field>
        <field name="view_mode">list,form</field>
    </record>

    <menuitem id="{{p}}_root" name="{{App}}"
              web_icon="{{module}},static/description/icon.png"/>
    <menuitem id="{{p}}_{{item}}_menu" name="{{Items}}" parent="{{p}}_root"
              action="{{p}}_{{item}}_action"/>

</odoo>
"""

MENUS_V2 = """\
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="{{p}}_{{item}}_action" model="ir.actions.act_window">
        <field name="name">{{Items}}</field>
        <field name="res_model">{{p}}.{{item}}</field>
        <field name="view_mode">list,form</field>
    </record>

    <record id="{{p}}_{{maker}}_action" model="ir.actions.act_window">
        <field name="name">{{Makers}}</field>
        <field name="res_model">{{p}}.{{maker}}</field>
        <field name="view_mode">list,form</field>
    </record>

    <menuitem id="{{p}}_root" name="{{App}}"
              web_icon="{{module}},static/description/icon.png"/>
    <menuitem id="{{p}}_{{item}}_menu" name="{{Items}}" parent="{{p}}_root"
              action="{{p}}_{{item}}_action" sequence="10"/>
    <menuitem id="{{p}}_{{maker}}_menu" name="{{Makers}}" parent="{{p}}_root"
              action="{{p}}_{{maker}}_action" sequence="20"/>

</odoo>
"""

FORM_V1 = """\
    <record id="{{p}}_{{item}}_view_form" model="ir.ui.view">
        <field name="name">{{p}}.{{item}}.view.form</field>
        <field name="model">{{p}}.{{item}}</field>
        <field name="arch" type="xml">
            <form string="{{Item}}">
                <sheet>
                    <h1><field name="name" placeholder="{{item_placeholder}}"/></h1>
                    <group>
                        <field name="{{maker}}"/>
                        <field name="{{date1}}"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>
"""

LIST_SEARCH_V1 = """\
    <record id="{{p}}_{{item}}_view_list" model="ir.ui.view">
        <field name="name">{{p}}.{{item}}.view.list</field>
        <field name="model">{{p}}.{{item}}</field>
        <field name="arch" type="xml">
            <list string="{{Items}}">
                <field name="name"/>
                <field name="{{maker}}"/>
                <field name="{{date1}}"/>
            </list>
        </field>
    </record>

    <record id="{{p}}_{{item}}_view_search" model="ir.ui.view">
        <field name="name">{{p}}.{{item}}.view.search</field>
        <field name="model">{{p}}.{{item}}</field>
        <field name="arch" type="xml">
            <search string="{{Items}}">
                <field name="name"/>
                <field name="{{maker}}"/>
                <filter name="{{filter1}}" string="{{Filter1}}"
                        domain="[('{{date1}}', '!=', False)]"/>
                <filter name="group_{{maker}}" string="{{Maker}}"
                        context="{'group_by': '{{maker}}'}"/>
            </search>
        </field>
    </record>
"""


def item_views(*records):
    return '<?xml version="1.0" encoding="utf-8"?>\n<odoo>\n\n' + '\n'.join(records) + '\n</odoo>\n'


FORM_V2 = FORM_V1.replace('<field name="{{maker}}"/>', '<field name="{{maker}}_id"/>')
LIST_SEARCH_V2 = (LIST_SEARCH_V1
                  .replace('<field name="{{maker}}"/>', '<field name="{{maker}}_id"/>')
                  .replace("'group_by': '{{maker}}'", "'group_by': '{{maker}}_id'"))

FORM_V3 = """\
    <record id="{{p}}_{{item}}_view_form" model="ir.ui.view">
        <field name="name">{{p}}.{{item}}.view.form</field>
        <field name="model">{{p}}.{{item}}</field>
        <field name="arch" type="xml">
            <form string="{{Item}}">
                <header>
                    <button name="{{take}}" type="object" string="{{Take}}"
                            class="btn-primary" invisible="state != 'available'"/>
                    <button name="{{give}}" type="object" string="{{Give}}"
                            invisible="state != '{{taken}}'"/>
                    <field name="state" widget="statusbar"/>
                </header>
                <sheet>
                    <h1><field name="name" placeholder="{{item_placeholder}}"/></h1>
                    <group>
                        <field name="{{maker}}_id"/>
                        <field name="{{date1}}"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>
"""

FORM_V4 = FORM_V3.replace("""                        <field name="{{date1}}"/>
                    </group>""", """                        <field name="{{date1}}"/>
                        <field name="{{date2}}" invisible="state != '{{taken}}'"/>
                        <field name="{{days}}" invisible="state != '{{taken}}'"/>
                    </group>""")

FORM_V5 = (FORM_V4
           .replace('<h1><field name="name" placeholder="{{item_placeholder}}"/></h1>',
                    '<h1><field name="name" placeholder="{{item_placeholder}}"\n'
                    '                               readonly="state == \'{{taken}}\'"/></h1>')
           .replace('<field name="{{maker}}_id"/>',
                    '<field name="{{maker}}_id" readonly="state == \'{{taken}}\'"/>')
           .replace('<field name="{{date2}}" invisible="state != \'{{taken}}\'"/>',
                    '<field name="{{date2}}" invisible="state != \'{{taken}}\'"\n'
                    '                               required="state == \'{{taken}}\'"/>'))

FORM_V6 = FORM_V5.replace("""                </sheet>
            </form>""", """                </sheet>
                <chatter/>
            </form>""")

AUTHOR_VIEWS = """\
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="{{p}}_{{maker}}_view_list" model="ir.ui.view">
        <field name="name">{{p}}.{{maker}}.view.list</field>
        <field name="model">{{p}}.{{maker}}</field>
        <field name="arch" type="xml">
            <list string="{{Makers}}">
                <field name="name"/>
            </list>
        </field>
    </record>

    <record id="{{p}}_{{maker}}_view_form" model="ir.ui.view">
        <field name="name">{{p}}.{{maker}}.view.form</field>
        <field name="model">{{p}}.{{maker}}</field>
        <field name="arch" type="xml">
            <form string="{{Maker}}">
                <sheet>
                    <h1><field name="name" placeholder="{{maker_placeholder}}"/></h1>
                </sheet>
            </form>
        </field>
    </record>

</odoo>
"""

DATA_V1 = ('security/ir.access.csv',)
DATA_V2 = ('security/ir.access.csv', 'views/{{p}}_menus.xml')
DATA_V3 = ('security/ir.access.csv', 'views/{{p}}_{{item}}_views.xml', 'views/{{p}}_menus.xml')
DATA_V4 = ('security/ir.access.csv', 'views/{{p}}_{{item}}_views.xml', 'views/{{p}}_{{maker}}_views.xml',
           'views/{{p}}_menus.xml')

# the Python side of the module, for Build it live
NAME = {'name': 'name', 'type': 'char', 'string': '{{Name}}', 'required': True}
BOOK_FIELDS_V1 = [
    NAME,
    {'name': '{{maker}}', 'type': 'char', 'string': '{{Maker}}'},
    {'name': '{{date1}}', 'type': 'date', 'string': '{{Date1}}'},
]

TEMPLATE = {
    'key': '{{key}}',
    'module': '{{module}}',
    # what See it opens: the model of the app, and its action (an id of the module)
    'main_model': '{{p}}.{{item}}',
    'main_action': '{{p}}_{{item}}_action',
    'name': _lt("Build a {{App}} app"),
    'summary': _lt("Your first Odoo app, from an empty folder to {{items}}, {{makers}}, buttons and a "
                   "computed field."),
    'minutes': 20,
    # Basic + a little more: the steps marked 'more', and what they need
    'more_minutes': 30,
    'more_depends': ['mail'],
    'level': _lt("Beginner"),
    'video_url': False,
    # Your turn: no code shown, the Academy checks
    'challenges': [
        {'key': 'notes', 'kind': 'field', 'model': '{{p}}.{{item}}', 'label': 'Notes', 'type': 'text', 'view': 'form',
         'title': _lt("A field of your own"),
         'todo': _lt("Add a field labelled Notes, of type Text, to your {{items}}, and show it on the form."),
         'hint_code': _lt("In the model, a fields.Text with the string Notes; in the form view, a field "
                          "element for it. Restart Odoo, then Upgrade."),
         'hint_live': _lt("Developer mode, then Settings > Technical > Models: open x_{{p}}_{{item}} and add "
                          "the field x_notes, labelled Notes, of type Text. Then Technical > Views: add it to "
                          "the form view of your {{items}}.")},
        {'key': 'filter', 'kind': 'filter', 'model': '{{p}}.{{item}}', 'label': 'Available',
         'title': _lt("A filter of your own"),
         'todo': _lt("Add a filter labelled Available to the search view: the {{items}} not {{taken}}."),
         'hint_code': _lt("In the search view, a filter element with the string Available and a domain on the "
                          "status. Upgrade."),
         'hint_live': _lt("Settings > Technical > Views: edit the search view of your {{items}}, and add the "
                          "filter there, with a domain on x_state.")},
        {'key': 'required', 'kind': 'required', 'model': '{{p}}.{{item}}', 'field': '{{maker}}_id',
         'title': _lt("No {{item}} without its {{maker}}"),
         'todo': _lt("Make the {{maker}} of a {{item}} required."),
         'hint_code': _lt("One argument on the field, in the model. Restart Odoo, then Upgrade."),
         'hint_live': _lt("Settings > Technical > Models: open x_{{p}}_{{item}}, then its field "
                          "x_{{maker}}_id: tick Required, and set On Delete to Restrict ({{makers}} still "
                          "in use cannot be deleted). In Python, Odoo does that by itself.")},
    ],
    'steps': [
        {
            'key': 'intro',
            'title': _lt("What we will build"),
            'intro': True,
            'preview': '/om_academy/static/img/{{key}}_preview.gif',
            'preview_more': '/om_academy/static/img/{{key}}_more_preview.gif',
            'explain': _lt(
                "<p>Every Odoo app you have used, Sales, Inventory, Contacts, started the same way: as "
                "an empty folder. We start from one too, and step by step it becomes <b>{{App}}</b>: a "
                "list of {{items}}, a page for each {{item}}, {{makers}}, <b>{{Take}}</b> and "
                "<b>{{Give}}</b> buttons, and a number of days that counts itself.</p><p>You do not "
                "need to know Odoo development. Each step adds one piece, and each piece answers a "
                "question the step before left open. Every new word is explained the first time you "
                "meet it, in the <b>New words</b> box. Pick how you want to build "
                "it:</p><ul><li><b>Code it</b>: you write the files in your editor, Odoo loads them, "
                "and the Academy checks your work after each step.</li><li><b>Build it live</b>: no "
                "editor needed. The Academy shows you the code of each step and creates the same thing "
                "in your database, so you see it appear at once.</li></ul><p>You can switch modes at "
                "any time.</p><p><b>Basic + a little more</b> adds what real apps have: fields locked "
                "or mandatory depending on the status, a place to discuss each {{item}}, and a history "
                "of changes.</p>"),
        },
        {
            'key': 'skeleton',
            'title': _lt("The module skeleton"),
            'explain': _lt(
                "<p>Let's begin where every Odoo app begins: with an empty folder. Sales, Inventory, "
                "Contacts: each one is nothing more than a folder of files that Odoo reads.</p><p>But "
                "Odoo does not open every folder on your computer. It looks only in the folders it was "
                "told about, its <b>addons path</b>, and it only takes a folder seriously when it "
                "carries a label saying what is inside. Think of a moving box: without a label, nobody "
                "knows what it holds or where it goes. So our first step is a folder, and its "
                "label.</p><dl><dt>module</dt><dd>An app, or a piece of one, as Odoo sees it: one "
                "folder of files. Install a module, and what it holds appears in Odoo.</dd><dt>addons "
                "path</dt><dd>The list of folders where Odoo looks for "
                "modules.</dd><dt>manifest</dt><dd>The label of the box: the file "
                "<code>__manifest__.py</code>. It tells Odoo the name of the app, its author, what it "
                "needs, and which of its files to read.</dd><dt>depends</dt><dd>The modules ours needs "
                "before it can work. We only need <code>base</code>, the heart of Odoo, present in "
                "every database.</dd><dt>Python package</dt><dd>A folder Python can load. The file "
                "<code>__init__.py</code> is what makes a folder one.</dd></dl><ul><li>the folder "
                "<code>{{module}}</code>: our module;</li><li><code>__manifest__.py</code>: the name "
                "<i>{{App}}</i>, you as the author, and <code>'depends': "
                "['base']</code>;</li><li><code>__init__.py</code>: empty for now. It only says “this "
                "folder is Python”;</li><li><code>static/description/icon.png</code>: your icon. Odoo "
                "looks for it at exactly this place, and shows it in Apps.</li></ul><p "
                "class=\"o_academy_story_next\">Install it, and Apps shows {{App}} with your name and "
                "your icon. So, is it finished? Not yet: there is nothing inside. It cannot keep a "
                "single {{item}}. Next step.</p>"),
            'files': {
                '__manifest__.py': manifest(),
                '__init__.py': '',
                ICON_PATH: ICON,
            },
            'live': [],
            'live_note': _lt(
                "Your first module is in <b>Apps</b>, installed: <b>{{App}}</b>, with your name as author and your "
                "icon. Odoo calls it an <i>imported</i> module: it lives in the database, with no folder. "
                "Click <b>See it in Odoo</b> and look, then come back for the next step. Uninstall it "
                "from Apps, and everything built live goes with it."),
            'code_note': _lt(
                "Create the folder <code>{{module}}</code> in your addons path with these files, or click <b>Write "
                "it for me</b>. Then tell Odoo: in <b>Apps</b>, <b>Update Apps List</b> (shown in "
                "developer mode), and search <i>{{App}}</i>: your module, with your name and your icon. "
                "Install it there, or click <b>Install</b> here, which does both."),
            'result_gif': '/om_academy/static/img/{{key}}_module.gif',
            'see': 'module',
            'see_text': _lt("Apps: your module, with your name and your icon."),
        },
        {
            'key': 'model',
            'title': _lt("A model to store {{items}}"),
            'explain': _lt(
                "<p>Our app exists: Odoo knows its name and its icon. But where would it keep a "
                "{{item}}? Nowhere yet. Everything Odoo knows, every customer, every invoice, is kept "
                "in a <b>database</b>, and a database keeps its data in <b>tables</b>.</p><p>A table "
                "is like a spreadsheet: columns across the top, <i>{{Name}}</i>, <i>{{Maker}}</i>, "
                "<i>{{Date1}}</i>, and one row for each {{item}}. In Odoo we never build that "
                "spreadsheet ourselves. We describe a {{item}} in Python, in a <b>model</b>, and Odoo "
                "builds the table from our description. Change the description later, and Odoo changes "
                "the table to match.</p><dl><dt>database</dt><dd>Where Odoo keeps all its data. Odoo "
                "uses PostgreSQL.</dd><dt>table</dt><dd>A spreadsheet inside the database: columns, "
                "and one row per thing stored.</dd><dt>model</dt><dd>The description of one kind of "
                "thing your app stores, here a {{item}}, written as a Python class. Odoo makes a table "
                "from it.</dd><dt>field</dt><dd>One piece of information of a {{item}}, like its "
                "{{name_lower}}. Each field becomes a column of the table.</dd><dt>record</dt><dd>One "
                "{{item}} saved by a user: one row of the table.</dd><dt>class</dt><dd>In Python, a "
                "named block of code that describes something. Ours describes a "
                "{{item}}.</dd></dl><ul><li><code>_name = '{{p}}.{{item}}'</code> names our model. The "
                "table gets the same name, with <code>_</code> for the dot: "
                "<code>{{p}}_{{item}}</code>;</li><li><code>fields.Char</code> holds a short text, "
                "like the {{name_lower}}; <code>fields.Date</code> holds a "
                "date;</li><li><code>required=True</code>: no {{item}} can be saved without its "
                "{{name_lower}};</li><li>the <code>import</code> lines of the two "
                "<code>__init__.py</code> files tell Python to load our new file. Forget them, and "
                "Odoo never sees the model.</li></ul><p class=\"o_academy_story_next\">The table is "
                "ready. Now open Odoo and look for our {{items}}: nothing, not even for you. Odoo has "
                "locked the door. Next step.</p>"),
            'files': {
                '__init__.py': "from . import models\n",
                'models/__init__.py': "from . import {{p}}_{{item}}\n",
                'models/{{p}}_{{item}}.py': BOOK_V1,
            },
            'live': [{'op': 'model', 'model': '{{p}}.{{item}}', 'string': '{{Item}}', 'fields': BOOK_FIELDS_V1}],
            'live_note': _lt(
                "Odoo stores your model as a record of <code>ir.model</code>, and each field as a "
                "record of <code>ir.model.fields</code>. A model created in the database must start "
                "with <code>x_</code>: yours is <code>x_{{p}}_{{item}}</code>, and its fields "
                "<code>x_name</code>, <code>x_{{maker}}</code>... In a module, it is "
                "<code>{{p}}.{{item}}</code>."),
            'code_note': _lt(
                "A new Python file needs Odoo to be <b>restarted</b>, then click <b>Upgrade</b>. "
                "Tip: start Odoo with <code>--dev=reload,xml</code> and it restarts by itself "
                "when you save a Python file."),
            'see': 'model',
            'see_text': _lt("Settings > Technical > Models: your model and its fields."),
        },
        {
            'key': 'access',
            'title': _lt("Access rights"),
            'explain': _lt(
                "<p>The table is ready, but Odoo will not let anyone use it. That is on purpose: when "
                "a new model appears, Odoo lets <b>nobody</b> touch its records until we say who "
                "may.</p><p>Think of a new room in an office building: it stays locked until someone "
                "hands out keys. In Odoo those keys are <b>access rights</b>. They are not given to "
                "people one by one, but to <b>groups</b>: teams of users, like <i>Employees</i> or "
                "<i>Sales Managers</i>. Give a key to a group, and everyone in it can open the "
                "door.</p><dl><dt>access right</dt><dd>A permission on one model, for one group: may "
                "its users create, read, change, delete the records?</dd><dt>group</dt><dd>A team of "
                "users. Users get their permissions from the groups they are "
                "in.</dd><dt>base.group_user</dt><dd>The technical name of the group <i>Internal "
                "User</i>: every employee who logs into Odoo is in it. <code>base</code> is the module "
                "that made it, <code>group_user</code> its name inside "
                "it.</dd><dt>crud</dt><dd>Create, Read, Update, Delete: the four things you can do "
                "with a record. <code>crud</code> allows all four; <code>r</code> alone would mean "
                "read only.</dd><dt>CSV file</dt><dd>A table as plain text: one line per row, the "
                "values separated by commas. Odoo loads it line by line into the "
                "database.</dd></dl><ul><li><code>security/ir.access.csv</code> holds one access "
                "right: our model, the group <code>base.group_user</code>, and <code>crud</code>. So "
                "every employee may do everything with {{items}};</li><li>the first line of the file "
                "names the columns; <code>ir.access</code>, the name of the file, is the model where "
                "Odoo keeps every access right;</li><li>the manifest now lists the file under "
                "<code>data</code>: Odoo loads only the files its manifest names.</li></ul><p "
                "class=\"o_academy_story_next\">Every employee may see our {{items}} now. But where? "
                "The home screen shows nothing to click for them. Next step.</p>"),
            'files': {
                '__manifest__.py': manifest(*DATA_V1),
                'security/ir.access.csv': ACCESS_V1,
            },
            'live': [],
            'live_note': _lt(
                "The Academy created the access right as a record of <code>ir.access</code>, "
                "exactly what loading the CSV file does."),
            'code_note': _lt("Add the file and its line in the manifest, then click <b>Upgrade</b>."),
            'see': 'model_access',
            'see_text': _lt("The access rights of your model."),
        },
        {
            'key': 'menu',
            'title': _lt("An action and a menu"),
            'explain': _lt(
                "<p>Users are allowed in, but there is no door. The home screen shows Sales, "
                "Contacts... and no {{App}}. We need something to click, and Odoo needs to know what "
                "to show once it is clicked.</p><p>Odoo splits that in two. The <b>menu</b> is what "
                "users see and click: a tile on the home screen, an entry in the bar at the top of an "
                "app. The <b>action</b> is the order behind it: “show the {{items}}, all of them in a "
                "list, and one at a time in a form”. A menu points to an action, like a doorbell wired "
                "to a door.</p><dl><dt>menu</dt><dd>An entry users click. Without a parent, it is a "
                "tile on the home screen; inside another menu, it is an entry in the top bar of the "
                "app.</dd><dt>action</dt><dd>An order Odoo runs when a menu or a button is clicked. "
                "Ours, a <i>window action</i>, opens the records of a model on the "
                "screen.</dd><dt>view</dt><dd>One way to show records on the screen: a <b>list</b> "
                "shows many, a <b>form</b> shows one.</dd><dt>XML</dt><dd>A text format made of tags, "
                "like a web page. Odoo reads its menus, actions and screens from XML "
                "files.</dd></dl><ul><li>the <code>record</code> of <code>ir.actions.act_window</code> "
                "is the action: it opens the model <code>{{p}}.{{item}}</code> as a list, then a form "
                "(<code>list,form</code>);</li><li>the first <code>menuitem</code> has no parent: it "
                "is the {{App}} tile, with your icon (<code>web_icon</code>);</li><li>the second one "
                "sits inside it, is called {{Items}}, and runs the action;</li><li>the manifest lists "
                "the new file under <code>data</code>.</li></ul><p "
                "class=\"o_academy_story_next\">Click {{App}}, then <i>New</i>: you can save your "
                "first {{item}}! We gave Odoo no form, so it drew one by itself: every field one under "
                "another, no title. It works, but it is plain. Next step.</p>"),
            'files': {
                '__manifest__.py': manifest(*DATA_V2),
                'views/{{p}}_menus.xml': MENUS_V1,
            },
            'live': [],
            'live_note': _lt(
                "The action is a record of <code>ir.actions.act_window</code>, the menus records "
                "of <code>ir.ui.menu</code>. Odoo shows them as soon as they exist."),
            'code_note': _lt("Add the file and its line in the manifest, then click <b>Upgrade</b>."),
            'see': 'app',
            'see_text': _lt("{{App}} is on your home screen. Open it and add a {{item}}!"),
        },
        {
            'key': 'form',
            'title': _lt("A form view"),
            'explain': _lt(
                "<p>Our first {{items}} are in, through the form Odoo drew by itself. It works, but it "
                "looks nothing like the forms of Sales or Contacts.</p><p>A <b>form</b> is the screen "
                "of one record, like a paper form: a title, labels, boxes to fill in. When we give "
                "Odoo none, it lists every field one under another. To decide what goes where, we "
                "write a <b>form view</b>: the layout of that screen, in "
                "XML.</p><dl><dt>form</dt><dd>The screen showing one record, where users read and type "
                "its fields.</dd><dt>form view</dt><dd>Our layout of that screen: which fields, in "
                "which order, where.</dd><dt>sheet</dt><dd>The white page in the middle of a form. "
                "Without it, the fields sit on the grey background.</dd><dt>h1</dt><dd>A big heading: "
                "the {{name_lower}} shows large, as the title of the page.</dd><dt>group</dt><dd>A "
                "block that lines fields up: the label on the left, the value on the "
                "right.</dd></dl><ul><li>the view is a record of <code>ir.ui.view</code>, the model "
                "where Odoo keeps every screen layout, for the model "
                "<code>{{p}}.{{item}}</code>;</li><li>inside <code>&lt;form&gt;</code>: a "
                "<code>sheet</code>, the {{name_lower}} in an <code>h1</code>, the {{maker}} and the "
                "date in a <code>group</code>;</li><li>the manifest lists the file before the menus: "
                "the action finds the view when it is loaded.</li></ul><p "
                "class=\"o_academy_story_next\">One {{item}} looks good now. But picture fifty of "
                "them: how does a user see them all, and find the one they need? Next step.</p>"),
            'files': {
                '__manifest__.py': manifest(*DATA_V3),
                'views/{{p}}_{{item}}_views.xml': item_views(FORM_V1),
            },
            'live': [],
            'live_note': _lt("The view is a record of <code>ir.ui.view</code>, its layout in the "
                             "<code>arch</code> field."),
            'code_note': _lt("Add the file before the menus in the manifest, then click "
                             "<b>Upgrade</b>."),
            'see': 'form',
            'see_text': _lt("Open a {{item}}: same data, new layout."),
        },
        {
            'key': 'list_search',
            'title': _lt("A list and a search view"),
            'explain': _lt(
                "<p>Each {{item}} has a proper form now. Picture fifty of them: users need to see them "
                "all at a glance, and to find one fast.</p><p>Two more views do that. The <b>list "
                "view</b> is the table you see when you open the app: one line per {{item}}, with the "
                "columns we choose. The <b>search view</b> decides what the search bar at the top "
                "offers: what you can type in, ready-made <b>filters</b>, and ways to <b>group</b> the "
                "lines.</p><dl><dt>list view</dt><dd>The screen of many records: one line each, the "
                "columns we pick. Odoo 20 writes it <code>&lt;list&gt;</code>; before Odoo 17, "
                "<code>&lt;tree&gt;</code>.</dd><dt>search view</dt><dd>What the search bar offers for "
                "a model: fields to search in, filters, group-bys.</dd><dt>filter</dt><dd>A ready-made "
                "search, one click away, like <i>{{Filter1}}</i>.</dd><dt>domain</dt><dd>The condition "
                "of a filter: a list of (field, operator, value). <code>[('{{date1}}', '!=', "
                "False)]</code> means “{{Date1}} is set”.</dd><dt>group by</dt><dd>Puts the lines in "
                "folders by the value of a field: all the {{items}} of one {{maker}} "
                "together.</dd></dl><ul><li><code>&lt;list&gt;</code>: the columns {{Name}}, {{Maker}} "
                "and {{Date1}};</li><li><code>&lt;search&gt;</code>: type a {{name_lower}} or a "
                "{{maker}} to search, the filter {{Filter1}}, and a group-by {{Maker}};</li><li>both "
                "go in the same file as the form: Odoo picks the right one for each "
                "screen.</li></ul><p class=\"o_academy_story_next\">Group the {{items}} by {{maker}}: "
                "one {{maker}} typed a little differently lands in two groups. Typing the {{maker}} "
                "again on every {{item}} is a problem. Next step.</p>"),
            'files': {
                'views/{{p}}_{{item}}_views.xml': item_views(FORM_V1, LIST_SEARCH_V1),
            },
            'live': [],
            'live_note': _lt("Two more records of <code>ir.ui.view</code>, of type list and search."),
            'code_note': _lt("Click <b>Upgrade</b>: only XML changed, no restart needed."),
            'see': 'list',
            'see_text': _lt("Try the {{Filter1}} filter, and group the {{items}} by {{maker}}."),
        },
        {
            'key': 'authors',
            'title': _lt("{{Makers}}: a second model and a link"),
            'explain': _lt(
                "<p>Every {{item}} carries its {{maker}} as text, typed again and again. One typo and "
                "the {{items}} of one {{maker}} split in two; rename a {{maker}}, and you edit every "
                "{{item}} one by one.</p><p>The cure: keep the {{makers}} in a table of their own, "
                "each one typed once, and let each {{item}} <b>point</b> to its {{maker}}. On the "
                "form, users no longer type a {{maker}}: they pick one from a list, or create it on "
                "the fly.</p><dl><dt>Many2one</dt><dd>A field that points to one record of another "
                "model. Many {{items}} can point to the same {{maker}}: many to one. Users see it as a "
                "dropdown.</dd><dt>id</dt><dd>The number Odoo gives each record. The link keeps the id "
                "of the {{maker}}, not its name: rename the {{maker}} once, and every {{item}} shows "
                "the new name.</dd><dt>_id</dt><dd>How Odoo names links: <code>{{maker}}_id</code> "
                "says “this field holds the id of a {{maker}}”.</dd></dl><ul><li>a second model, "
                "<code>{{p}}.{{maker}}</code>, with everything a model needs and you already know: its "
                "access right, its views, its menu and action;</li><li>on the {{item}}, the text field "
                "<code>{{maker}}</code> is replaced by <code>{{maker}}_id = "
                "fields.Many2one('{{p}}.{{maker}}')</code>;</li><li>the views of the {{item}} now show "
                "<code>{{maker}}_id</code>, and the list groups by it.</li></ul><p "
                "class=\"o_academy_story_next\">Our data is clean now. But the app only stores "
                "{{items}}: nothing ever happens to them. Next step.</p>"),
            'files': {
                '__manifest__.py': manifest(*DATA_V4),
                'models/__init__.py': "from . import {{p}}_{{maker}}\nfrom . import {{p}}_{{item}}\n",
                'models/{{p}}_{{maker}}.py': AUTHOR,
                'models/{{p}}_{{item}}.py': BOOK_V2,
                'security/ir.access.csv': ACCESS_V2,
                'views/{{p}}_{{maker}}_views.xml': AUTHOR_VIEWS,
                'views/{{p}}_{{item}}_views.xml': item_views(FORM_V2, LIST_SEARCH_V2),
                'views/{{p}}_menus.xml': MENUS_V2,
            },
            'live': [
                {'op': 'model', 'model': '{{p}}.{{maker}}', 'string': '{{Maker}}',
                 'fields': [{'name': 'name', 'type': 'char', 'string': 'Name', 'required': True}]},
                {'op': 'field', 'model': '{{p}}.{{item}}', 'name': '{{maker}}_id', 'type': 'many2one',
                 'relation': '{{p}}.{{maker}}', 'string': '{{Maker}}'},
                {'op': 'drop_field', 'model': '{{p}}.{{item}}', 'name': '{{maker}}', 'after_xml': True},
            ],
            'live_note': _lt(
                "A second model, <code>x_{{p}}_{{maker}}</code>, and a field "
                "<code>x_{{maker}}_id</code> of type many2one on the {{items}}. The old text field "
                "<code>x_{{maker}}</code> is removed once the views no longer use it."),
            'code_note': _lt("A new Python file: <b>restart</b> Odoo, then click <b>Upgrade</b>."),
            'see': 'form',
            'see_text': _lt("The {{maker}} of a {{item}} is now a link: pick one, or create it on the fly."),
        },
        {
            'key': 'buttons',
            'title': _lt("A status and buttons"),
            'explain': _lt(
                "<p>Our {{items}} sit there, neatly stored. But {{App}} is about what happens to them: "
                "a {{item}} is {{taken}}, then it is available again. The app must know where each "
                "{{item}} is, and let users change it in one click.</p><p>So the {{item}} gets a "
                "<b>status</b>, a field with a fixed list of choices, and the form gets two "
                "<b>buttons</b>. Clicking a button runs a small piece of Python in the model, a "
                "<b>method</b>, which writes the new status.</p><dl><dt>Selection</dt><dd>A field with "
                "a fixed list of choices: here Available or "
                "{{Taken}}.</dd><dt>button</dt><dd>Something to click on a form. A button of type "
                "<code>object</code> runs the method of the model that has its "
                "name.</dd><dt>method</dt><dd>A function written inside the model's class: something a "
                "record can do. <code>{{take}}</code> marks the {{item}} "
                "{{taken}}.</dd><dt>self.write</dt><dd>Changes fields of the record, and saves them: "
                "<code>self.write({'state': '{{taken}}'})</code>.</dd><dt>statusbar</dt><dd>The steps "
                "shown at the top right of a form, the current one "
                "highlighted.</dd></dl><ul><li><code>state = fields.Selection(...)</code>, Available "
                "by default;</li><li>two methods, <code>{{take}}</code> and <code>{{give}}</code>, "
                "each writing a status;</li><li>in the form, a <code>&lt;header&gt;</code> with the "
                "two buttons and the status bar;</li><li><code>invisible=\"state != "
                "'available'\"</code>: {{Take}} shows only when the {{item}} is available, {{Give}} "
                "only when it is {{taken}}.</li></ul><p class=\"o_academy_story_next\">We know a "
                "{{item}} is {{taken}} now. But since when? For how many days? Someone would have to "
                "count. Next step.</p>"),
            'files': {
                'models/{{p}}_{{item}}.py': BOOK_V3,
                'views/{{p}}_{{item}}_views.xml': item_views(FORM_V3, LIST_SEARCH_V2),
            },
            'live': [
                {'op': 'field', 'model': '{{p}}.{{item}}', 'name': 'state', 'type': 'selection',
                 'string': 'Status', 'required': True, 'default': 'available',
                 'selection': [('available', 'Available'), ('{{taken}}', '{{Taken}}')]},
                {'op': 'method', 'model': '{{p}}.{{item}}', 'name': '{{take}}', 'string': '{{Take}}',
                 'code': "records.write({'x_state': '{{taken}}'})"},
                {'op': 'method', 'model': '{{p}}.{{item}}', 'name': '{{give}}', 'string': '{{Give}}',
                 'code': "records.write({'x_state': 'available'})"},
            ],
            'live_note': _lt(
                "A method cannot live in the database, so each button calls a <b>server "
                "action</b> (<code>ir.actions.server</code>) holding the same code. The default "
                "status is a record of <code>ir.default</code>."),
            'code_note': _lt("Python changed: <b>restart</b> Odoo, then click <b>Upgrade</b>."),
            'see': 'form',
            'see_text': _lt("Open a {{item}} and click {{Take}}: the status bar moves."),
        },
        {
            'key': 'compute',
            'title': _lt("A computed field"),
            'explain': _lt(
                "<p>A {{item}} can be {{taken}} now, and the next question comes naturally: for how "
                "long? We could ask users to type the number of days every morning... or let Odoo "
                "count.</p><p>First, {{Take}} also notes the date, in a new field <i>{{Date2}}</i>. "
                "Then a <b>computed field</b> gives the days: nobody types it, a method works it out "
                "from the date, each time the {{item}} is shown.</p><dl><dt>computed field</dt><dd>A "
                "field filled by a method instead of a user. It is not stored in the table: there is "
                "no column for it.</dd><dt>@api.depends</dt><dd>A line above the method naming the "
                "fields it reads. When one of them changes, Odoo works the value out again. Forgetting "
                "it is the most common bug.</dd><dt>for ... in self</dt><dd>A method receives one "
                "record or many: the loop does the count for each "
                "{{item}}.</dd></dl><ul><li><code>{{date2}} = fields.Date()</code>, written by "
                "{{Take}}, cleared by {{Give}};</li><li><code>{{days}} = "
                "fields.Integer(compute='_compute_{{days}}')</code>;</li><li>the method: for each "
                "{{item}} {{taken}}, today minus {{Date2}}, in days; 0 otherwise;</li><li>in the form, "
                "both fields show only while the {{item}} is {{taken}}.</li></ul><p "
                "class=\"o_academy_story_next\">Our app stores, shows, finds, links, acts and counts: "
                "a real app. Let's see what is next.</p>"),
            'files': {
                'models/{{p}}_{{item}}.py': BOOK_V4,
                'views/{{p}}_{{item}}_views.xml': item_views(FORM_V4, LIST_SEARCH_V2),
            },
            'live': [
                {'op': 'field', 'model': '{{p}}.{{item}}', 'name': '{{date2}}', 'type': 'date',
                 'string': '{{Date2}}'},
                {'op': 'field', 'model': '{{p}}.{{item}}', 'name': '{{days}}', 'type': 'integer',
                 'string': '{{Days}}', 'depends': 'x_{{date2}}, x_state',
                 'compute': (
                     "today = datetime.date.today()\n"
                     "for {{item}} in self:\n"
                     "    if {{item}}.x_state == '{{taken}}' and {{item}}.x_{{date2}}:\n"
                     "        {{item}}['x_{{days}}'] = (today - {{item}}.x_{{date2}}).days\n"
                     "    else:\n"
                     "        {{item}}['x_{{days}}'] = 0\n")},
                {'op': 'method', 'model': '{{p}}.{{item}}', 'name': '{{take}}', 'string': '{{Take}}',
                 'code': "records.write({'x_state': '{{taken}}', 'x_{{date2}}': datetime.date.today()})"},
                {'op': 'method', 'model': '{{p}}.{{item}}', 'name': '{{give}}', 'string': '{{Give}}',
                 'code': "records.write({'x_state': 'available', 'x_{{date2}}': False})"},
            ],
            'live_note': _lt(
                "A computed field created in the database holds its code in "
                "<code>ir.model.fields</code>, with its dependencies; the server actions of "
                "{{Take}} and {{Give}} now note the date."),
            'code_note': _lt("Python changed: <b>restart</b> Odoo, then click <b>Upgrade</b>."),
            'checks': [{'kind': 'compute', 'model': '{{p}}.{{item}}', 'field': '{{days}}',
                        'depends': ['{{date2}}', 'state']}],
            'see': 'form',
            'see_text': _lt("{{Take}} a {{item}}: the days {{taken}} fill themselves."),
        },
        {
            'key': 'conditions',
            'level': 'more',
            'title': _lt("Read-only and required, when it depends"),
            'explain': _lt(
                "<p>Here is a problem every real app meets: a {{item}} is {{taken}}, and someone "
                "changes its {{name_lower}} or its {{maker}}, or leaves <i>{{Date2}}</i> empty. Our "
                "form allows anything, at any time.</p><p>A field on a form can follow the record: "
                "locked, mandatory or hidden only when a <b>condition</b> is true. Odoo checks the "
                "condition as the user types, and the form changes at "
                "once.</p><dl><dt>readonly</dt><dd>Shown, but it cannot be "
                "changed.</dd><dt>required</dt><dd>Must be filled before the record can be "
                "saved.</dd><dt>condition</dt><dd>A small Python test on the fields of the record, "
                "like <code>state == '{{taken}}'</code>: true or "
                "false.</dd></dl><ul><li><code>readonly=\"state == '{{taken}}'\"</code> on the "
                "{{name_lower}} and the {{maker}}: locked while "
                "{{taken}};</li><li><code>required=\"state == '{{taken}}'\"</code> on {{Date2}}: "
                "mandatory while {{taken}};</li><li><code>required=True</code> in Python, as for the "
                "{{name_lower}}, applies always. Before Odoo 17, conditions were written "
                "<code>attrs=\"{'readonly': [...]}\"</code>.</li></ul><p "
                "class=\"o_academy_story_next\">The data is safe now. But when something goes wrong, "
                "where do people talk about a {{item}}? Next step.</p>"),
            'files': {
                'views/{{p}}_{{item}}_views.xml': item_views(FORM_V5, LIST_SEARCH_V2),
            },
            'live': [],
            'live_note': _lt("Only the form view changed: its <code>arch</code> holds the "
                             "conditions, on the <code>x_</code> fields."),
            'code_note': _lt("Only XML changed: click <b>Upgrade</b>, no restart needed."),
            'result_gif': '/om_academy/static/img/{{key}}_conditions.gif',
            'see': 'form',
            'see_text': _lt("Open a {{item}} and click {{Take}}: the {{name_lower}} and the {{maker}} lock."),
        },
        {
            'key': 'chatter',
            'level': 'more',
            'title': _lt("A chatter"),
            'explain': _lt(
                "<p>Colleagues have questions about a {{item}}: who has it, why, until when? Today "
                "they ask by email, far from the {{item}} itself.</p><p>Every Odoo app answers that "
                "the same way: the <b>chatter</b>, the column of messages next to a form. People write "
                "notes and emails right on the {{item}}, and <b>followers</b> get them. We do not "
                "build it: we reuse it from Discuss, a module Odoo already "
                "has.</p><dl><dt>chatter</dt><dd>The column of messages beside a form: notes, emails, "
                "followers, history.</dd><dt>follower</dt><dd>Someone who receives the messages of a "
                "record.</dd><dt>mail</dt><dd>The technical name of Discuss, the module that brings "
                "the chatter.</dd><dt>_inherit</dt><dd>Takes in the features of another model. With "
                "<code>mail.thread</code>, our {{item}} gains messages and followers, and stays a "
                "{{item}}.</dd></dl><ul><li>the manifest now <code>depends</code> on "
                "<code>mail</code>: Odoo installs Discuss first;</li><li><code>_inherit = "
                "['mail.thread']</code> under "
                "<code>_name</code>;</li><li><code>&lt;chatter/&gt;</code> after the sheet shows it on "
                "the form.</li></ul><p class=\"o_academy_story_next\">People can talk about a {{item}} "
                "now. But the {{item}} itself still forgets: who changed its status, and when? Next "
                "step.</p>"),
            'files': {
                '__manifest__.py': manifest(*DATA_V4, depends=('base', 'mail')),
                'models/{{p}}_{{item}}.py': BOOK_V5,
                'views/{{p}}_{{item}}_views.xml': item_views(FORM_V6, LIST_SEARCH_V2),
            },
            'live': [{'op': 'mail_thread', 'model': '{{p}}.{{item}}'}],
            'live_note': _lt(
                "The model's box <b>Mail Thread</b> (<code>is_mail_thread</code> of "
                "<code>ir.model</code>) is ticked, and the form shows the chatter. Odoo never "
                "unticks it: Undo takes the chatter off the form only."),
            'code_note': _lt("Python and the manifest changed: <b>restart</b> Odoo, then click "
                             "<b>Upgrade</b>. Odoo installs Discuss if it is not yet."),
            'checks': [{'kind': 'mail_thread', 'model': '{{p}}.{{item}}'}],
            'result_gif': '/om_academy/static/img/{{key}}_chatter.gif',
            'see': 'form',
            'see_text': _lt("Open a {{item}}: log a note in the chatter."),
        },
        {
            'key': 'tracking',
            'level': 'more',
            'title': _lt("Track the changes"),
            'explain': _lt(
                "<p>The chatter shows what people write. But when a status changes, nobody writes it "
                "down, and a week later nobody remembers.</p><p>Odoo can write it for us. Mark a field "
                "as <b>tracked</b>, and every change of it lands in the chatter by itself: who changed "
                "it, when, from what to what.</p><dl><dt>tracking</dt><dd>On a model with a chatter: "
                "each change of the field is noted in it.</dd></dl><ul><li><code>tracking=True</code> "
                "on the status and on the {{maker}}.</li></ul><p class=\"o_academy_story_next\">That "
                "was the last piece. Let's look at what you built.</p>"),
            'files': {
                'models/{{p}}_{{item}}.py': BOOK_V6,
            },
            'live': [{'op': 'tracking', 'model': '{{p}}.{{item}}', 'fields': ['state', '{{maker}}_id']}],
            'live_note': _lt("The fields' <b>tracking</b> (of <code>ir.model.fields</code>) is set."),
            'code_note': _lt("Python changed: <b>restart</b> Odoo, then click <b>Upgrade</b>."),
            'checks': [{'kind': 'tracking', 'model': '{{p}}.{{item}}', 'fields': ['state', '{{maker}}_id']}],
            'result_gif': '/om_academy/static/img/{{key}}_tracking.gif',
            'see': 'form',
            'see_text': _lt("{{Take}} a {{item}}: the chatter notes Available to {{Taken}}."),
        },
        {
            'key': 'finish',
            'title': _lt("Your app is done"),
            'finish': True,
            'explain': _lt(
                "<p>Remember the empty folder? It is <b>{{App}}</b> now: 2 models, 5 views, 3 menus, 2 "
                "buttons and a computed field. Open it from the home screen: a real Odoo app, and you "
                "wrote it.</p><p><b>Export as app</b> gives you the module as a zip: the very files of "
                "this course, ready to install on another database or to keep building in your "
                "editor.</p>"),
            'explain_more': _lt(
                "<p>Remember the empty folder? It is <b>{{App}}</b> now: 2 models, 5 views, 3 menus, 2 "
                "buttons, a computed field, fields that lock while a {{item}} is {{taken}}, and a "
                "chatter that keeps the history. Open it from the home screen: a real Odoo app, and "
                "you wrote it.</p><p><b>Export as app</b> gives you the module as a zip: the very "
                "files of this course, ready to install on another database or to keep building in "
                "your editor.</p>"),
            'files': {},
            'see': 'app',
            'see_text': _lt("Your app, on the home screen."),
        },
    ],
}


THEMES = [
    {'key': 'library', 'module': 'learn_library', 'App': 'Library', 'p': 'library', 'Cls': 'Library',
     'item': 'book', 'Item': 'Book', 'items': 'books', 'Items': 'Books',
     'maker': 'author', 'Maker': 'Author', 'makers': 'authors', 'Makers': 'Authors',
     'Name': 'Title', 'name_lower': 'title', 'item_placeholder': 'Book title', 'maker_placeholder': 'Author name',
     'date1': 'date_published', 'Date1': 'Published On', 'filter1': 'published', 'Filter1': 'Published',
     'taken': 'borrowed', 'Taken': 'Borrowed', 'take': 'action_borrow', 'Take': 'Borrow',
     'give': 'action_return', 'Give': 'Return', 'date2': 'date_borrowed', 'Date2': 'Borrowed On',
     'days': 'days_borrowed', 'Days': 'Days Borrowed', 'icon': 'book'},
    {'key': 'car_rental', 'module': 'learn_car_rental', 'App': 'Car Rental', 'p': 'rental', 'Cls': 'Rental',
     'item': 'car', 'Item': 'Car', 'items': 'cars', 'Items': 'Cars',
     'maker': 'brand', 'Maker': 'Brand', 'makers': 'brands', 'Makers': 'Brands',
     'Name': 'Name', 'name_lower': 'name', 'item_placeholder': 'Car name', 'maker_placeholder': 'Brand name',
     'date1': 'date_bought', 'Date1': 'Bought On', 'filter1': 'bought', 'Filter1': 'Bought',
     'taken': 'rented', 'Taken': 'Rented', 'take': 'action_rent', 'Take': 'Rent',
     'give': 'action_return', 'Give': 'Return', 'date2': 'date_rented', 'Date2': 'Rented On',
     'days': 'days_rented', 'Days': 'Days Rented', 'icon': 'car'},
    {'key': 'hotel', 'module': 'learn_hotel', 'App': 'Hotel', 'p': 'hotel', 'Cls': 'Hotel',
     'item': 'room', 'Item': 'Room', 'items': 'rooms', 'Items': 'Rooms',
     'maker': 'category', 'Maker': 'Category', 'makers': 'categories', 'Makers': 'Categories',
     'Name': 'Number', 'name_lower': 'number', 'item_placeholder': 'Room number', 'maker_placeholder': 'Category name',
     'date1': 'date_renovated', 'Date1': 'Renovated On', 'filter1': 'renovated', 'Filter1': 'Renovated',
     'taken': 'occupied', 'Taken': 'Occupied', 'take': 'action_check_in', 'Take': 'Check In',
     'give': 'action_check_out', 'Give': 'Check Out', 'date2': 'date_occupied', 'Date2': 'Occupied Since',
     'days': 'days_occupied', 'Days': 'Days Occupied', 'icon': 'bed'},
    {'key': 'tool_lending', 'module': 'learn_tool_lending', 'App': 'Tool Lending', 'p': 'lending', 'Cls': 'Lending',
     'item': 'tool', 'Item': 'Tool', 'items': 'tools', 'Items': 'Tools',
     'maker': 'brand', 'Maker': 'Brand', 'makers': 'brands', 'Makers': 'Brands',
     'Name': 'Name', 'name_lower': 'name', 'item_placeholder': 'Tool name', 'maker_placeholder': 'Brand name',
     'date1': 'date_bought', 'Date1': 'Bought On', 'filter1': 'bought', 'Filter1': 'Bought',
     'taken': 'lent', 'Taken': 'Lent', 'take': 'action_lend', 'Take': 'Lend',
     'give': 'action_return', 'Give': 'Return', 'date2': 'date_lent', 'Date2': 'Lent On',
     'days': 'days_lent', 'Days': 'Days Lent', 'icon': 'wrench'},
]

TOKEN = re.compile(r'\{\{(\w+)\}\}')


def fill_text(text, theme):
    return TOKEN.sub(lambda match: theme[match.group(1)], text)


class ThemedText:
    """ A text of the course, translated when shown, in the words of the subject. """

    def __init__(self, text, theme):
        self.text = text
        self.theme = theme

    def __str__(self):
        # the language given: Odoo would look for it in the code calling, which is this
        lang = request.env.lang if request and getattr(request, 'env', None) else None
        return fill_text(self.text._translate(lang or 'en_US'), self.theme)


def fill(value, theme):
    if isinstance(value, str):
        return fill_text(value, theme)
    if isinstance(value, dict):
        return {fill(key, theme): fill(item, theme) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(fill(item, theme) for item in value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return ThemedText(value, theme)  # a text to translate


def make_course(theme):
    course = fill(TEMPLATE, theme)
    course.update(family='first_app', subject=theme['App'], default_icon=theme['icon'])
    return course


COURSES = [make_course(theme) for theme in THEMES]
