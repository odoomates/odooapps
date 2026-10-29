# Course 2: extend what Odoo already has. A membership added to the contacts:
# fields through _inherit, Odoo's own views changed with XPath, and a computed
# field. Built live, the fields are custom ones (x_) on res.partner itself.
from odoo.tools.translate import LazyTranslate

from ..models.course_files import ICON, ICON_PATH

_lt = LazyTranslate(__name__)

MANIFEST = """\
{
    'name': 'Contact Members',
    'version': '1.0',
    'summary': 'A membership on the contacts',
    'depends': ['base'],
    'data': [%s],
    'license': 'LGPL-3',
}
"""


def manifest(*data):
    return MANIFEST % (''.join('\n        %r,' % path for path in data) + ('\n    ' if data else ''))


PARTNER_V1 = """\
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    member_level = fields.Selection(
        [('bronze', 'Bronze'), ('silver', 'Silver'), ('gold', 'Gold')], string='Member Level')
    member_since = fields.Date(string='Member Since')
"""

PARTNER_V2 = """\
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    member_level = fields.Selection(
        [('bronze', 'Bronze'), ('silver', 'Silver'), ('gold', 'Gold')], string='Member Level')
    member_since = fields.Date(string='Member Since')
    member_years = fields.Integer(string='Years a Member', compute='_compute_member_years')

    @api.depends('member_since')
    def _compute_member_years(self):
        today = fields.Date.context_today(self)
        for partner in self:
            if partner.member_since:
                partner.member_years = (today - partner.member_since).days // 365
            else:
                partner.member_years = 0
"""

FORM_V1 = """\
    <record id="view_partner_form" model="ir.ui.view">
        <field name="name">res.partner.view.form.inherit.learn_contacts</field>
        <field name="model">res.partner</field>
        <field name="inherit_id" ref="base.view_partner_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='category_id']" position="after">
                <field name="member_level"/>
                <field name="member_since"/>
            </xpath>
        </field>
    </record>
"""

FORM_V2 = FORM_V1.replace("""                <field name="member_since"/>
""", """                <field name="member_since"/>
                <field name="member_years" invisible="not member_since"/>
""")

LIST_SEARCH = """\
    <record id="view_partner_tree" model="ir.ui.view">
        <field name="name">res.partner.view.list.inherit.learn_contacts</field>
        <field name="model">res.partner</field>
        <field name="inherit_id" ref="base.view_partner_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='complete_name']" position="after">
                <field name="member_level" optional="show"/>
            </xpath>
        </field>
    </record>

    <record id="view_res_partner_filter" model="ir.ui.view">
        <field name="name">res.partner.view.search.inherit.learn_contacts</field>
        <field name="model">res.partner</field>
        <field name="inherit_id" ref="base.view_res_partner_filter"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='category_id']" position="after">
                <field name="member_level"/>
                <filter name="gold_members" string="Gold Members"
                        domain="[('member_level', '=', 'gold')]"/>
                <filter name="group_member_level" string="Member Level"
                        context="{'group_by': 'member_level'}"/>
            </xpath>
        </field>
    </record>
"""


def views(*records):
    return '<?xml version="1.0" encoding="utf-8"?>\n<odoo>\n\n' + '\n'.join(records) + '\n</odoo>\n'


LEVEL = {'name': 'member_level', 'type': 'selection', 'string': 'Member Level',
         'selection': [('bronze', 'Bronze'), ('silver', 'Silver'), ('gold', 'Gold')]}

COURSE = {
    'key': 'contacts',
    'app_name': 'Contact Members',
    'challenges': [
        {'key': 'number', 'kind': 'field', 'model': 'res.partner', 'label': 'Member Number', 'type': 'char',
         'view': 'form', 'title': _lt("A member number"),
         'todo': _lt("Add a field labelled Member Number, of type Char, to the contacts, and show it on "
                     "the contact form."),
         'hint_code': _lt("A fields.Char in your _inherit of res.partner, and one more field element in your "
                          "inherited form view. Restart Odoo, then Upgrade."),
         'hint_live': _lt("Settings > Technical > Models: open res.partner and add x_member_number. Then "
                          "Technical > Views: add it to your inherited view of the contact form.")},
        {'key': 'gold', 'kind': 'filter', 'model': 'res.partner', 'label': 'Silver Members',
         'title': _lt("A filter for silver members"),
         'todo': _lt("Add a filter labelled Silver Members to the contacts' search view."),
         'hint_code': _lt("Like Gold Members, in your inherited search view. Upgrade."),
         'hint_live': _lt("Settings > Technical > Views: your inherited search view of the contacts, like Gold "
                          "Members.")},
    ],
    'module': 'learn_contacts',
    'main_model': 'res.partner',
    'main_action': 'base.action_partner_form',
    'name': _lt("Extend Odoo: members in Contacts"),
    'summary': _lt("Add your own fields to Odoo's contacts, show them in Odoo's own screens with "
                   "XPath, and compute a value: the heart of customizing Odoo."),
    'minutes': 15,
    'level': _lt("Beginner"),
    'video_url': False,
    'steps': [
        {
            'key': 'intro',
            'title': _lt("What we will build"),
            'intro': True,
            'preview': '/om_academy/static/img/contacts_preview.gif',
            'explain': _lt(
                "<p>Most Odoo work is not new apps: it is <b>changing the apps Odoo has</b>. In "
                "this course you give the contacts a <b>membership</b>: a level (Bronze, Silver, "
                "Gold), the date they joined, and the years they have been a member, shown in "
                "Odoo's own contact form, list and search.</p>"
                "<p>You never touch Odoo's code: your module adds to it.</p>"),
        },
        {
            'key': 'skeleton',
            'title': _lt("The module skeleton"),
            'explain': _lt(
                "<p>The same two files as for any module. Contacts are in the "
                "<code>base</code> module, so that is all we depend on.</p>"),
            'files': {'__manifest__.py': manifest(), '__init__.py': '', ICON_PATH: ICON},
            'live': [],
            'live_note': _lt(
                "Your first module is in <b>Apps</b>, installed: <b>Contact Members</b>, with your name as author and your "
                "icon. Odoo calls it an <i>imported</i> module: it lives in the database, with no folder. "
                "Click <b>See it in Odoo</b> and look, then come back for the next step. Uninstall it "
                "from Apps, and everything built live goes with it."),
            'code_note': _lt(
                "Create the folder <code>learn_contacts</code> in your addons path with these files, or click <b>Write "
                "it for me</b>. Then tell Odoo: in <b>Apps</b>, <b>Update Apps List</b> (shown in "
                "developer mode), and search <i>Contact Members</i>: your module, with your name and your icon. "
                "Install it there, or click <b>Install</b> here, which does both."),
            'see': 'module',
            'see_text': _lt("Apps: your module, with your name and your icon."),
        },
        {
            'key': 'inherit',
            'title': _lt("Add fields to the contacts"),
            'explain': _lt(
                "<p><code>_inherit = 'res.partner'</code> without a <code>_name</code> does not "
                "create a model: it <b>adds to</b> the existing one. Every field you declare "
                "becomes a column of the contacts' table, next to Odoo's own fields.</p>"),
            'files': {
                '__init__.py': "from . import models\n",
                'models/__init__.py': "from . import res_partner\n",
                'models/res_partner.py': PARTNER_V1,
            },
            'live': [
                dict(LEVEL, op='field', model='res.partner'),
                {'op': 'field', 'model': 'res.partner', 'name': 'member_since', 'type': 'date',
                 'string': 'Member Since'},
            ],
            'live_note': _lt(
                "Two custom fields on <code>res.partner</code> itself: <code>x_member_level</code> "
                "and <code>x_member_since</code>. A field created in the database starts with "
                "<code>x_</code>, even on a model of Odoo."),
            'code_note': _lt("A new Python file: <b>restart</b> Odoo, then click <b>Upgrade</b>."),
            'see': 'model',
            'see_text': _lt("Settings > Technical > Models > Contact: your fields are among Odoo's."),
        },
        {
            'key': 'form',
            'title': _lt("Show them in Odoo's form, with XPath"),
            'explain': _lt(
                "<p>You do not copy Odoo's form: you <b>inherit</b> it. <code>inherit_id</code> "
                "names the view to change, and an <code>xpath</code> finds the place: "
                "<code>//field[@name='category_id']</code> is the Tags field. "
                "<code>position=\"after\"</code> puts your fields right after it; "
                "<code>before</code>, <code>inside</code> and <code>replace</code> exist too.</p>"
                "<p>As Odoo's coding guidelines ask, the inheriting view keeps the id of the view "
                "it changes (<code>view_partner_form</code>, in your module) and its name says "
                "so: <code>res.partner.view.form.inherit.learn_contacts</code>.</p>"),
            'files': {
                '__manifest__.py': manifest('views/res_partner_views.xml'),
                'views/res_partner_views.xml': views(FORM_V1),
            },
            'live': [],
            'live_note': _lt("An inherited view is a record of <code>ir.ui.view</code> with an "
                             "<code>inherit_id</code>: Odoo merges it into the contact form."),
            'code_note': _lt("Add the file and its line in the manifest, then click <b>Upgrade</b>."),
            'see': 'form',
            'see_text': _lt("Open a contact: the member fields are right after the tags."),
        },
        {
            'key': 'list_search',
            'title': _lt("A column, a filter and a group-by"),
            'explain': _lt(
                "<p>The same trick on the list and the search views: a column after the name "
                "(<code>optional=\"show\"</code> lets users hide it), a <b>Gold Members</b> "
                "filter, and a group-by on the level.</p>"),
            'files': {'views/res_partner_views.xml': views(FORM_V1, LIST_SEARCH)},
            'live': [],
            'live_note': _lt("Two more inherited views, of the contact list and of its search."),
            'code_note': _lt("Click <b>Upgrade</b>: only XML changed."),
            'see': 'list',
            'see_text': _lt("Contacts: try the Gold Members filter, and group them by level."),
        },
        {
            'key': 'compute',
            'title': _lt("Years of membership, computed"),
            'explain': _lt(
                "<p>A computed field on a model of Odoo works like on your own. "
                "<code>@api.depends('member_since')</code> keeps it right when the date changes, "
                "and <code>invisible=\"not member_since\"</code> hides it for non-members.</p>"),
            'files': {
                'models/res_partner.py': PARTNER_V2,
                'views/res_partner_views.xml': views(FORM_V2, LIST_SEARCH),
            },
            'live': [
                {'op': 'field', 'model': 'res.partner', 'name': 'member_years', 'type': 'integer',
                 'string': 'Years a Member', 'depends': 'x_member_since',
                 'compute': (
                     "today = datetime.date.today()\n"
                     "for partner in self:\n"
                     "    if partner.x_member_since:\n"
                     "        partner['x_member_years'] = (today - partner.x_member_since).days // 365\n"
                     "    else:\n"
                     "        partner['x_member_years'] = 0\n")},
            ],
            'live_note': _lt("A computed custom field on the contacts, with its code and its "
                             "dependency."),
            'code_note': _lt("Python changed: <b>restart</b> Odoo, then click <b>Upgrade</b>."),
            'checks': [{'kind': 'compute', 'model': 'res.partner', 'field': 'member_years',
                        'depends': ['member_since']}],
            'see': 'form',
            'see_text': _lt("Set a Member Since date on a contact: the years follow."),
        },
        {
            'key': 'finish',
            'title': _lt("You extended Odoo"),
            'finish': True,
            'explain': _lt(
                "<p>Three fields on Odoo's contacts, and three of Odoo's views extended "
                "without changing a line of Odoo: that is how every Odoo app is customized.</p>"
                "<p><b>Export as app</b> gives you the module as a zip.</p>"),
            'files': {},
            'see': 'list',
            'see_text': _lt("Your members, in Contacts."),
        },
    ],
}
