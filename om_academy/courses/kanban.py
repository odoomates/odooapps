# Course: organize with a Kanban board. An app of ideas, its stages as data
# loaded from an XML file, each idea in a stage, then the board: cards in
# columns, dragged from stage to stage, with colors and priority stars.
from odoo.tools.translate import LazyTranslate

from ..models.course_files import ICON, ICON_PATH

_lt = LazyTranslate(__name__)

MANIFEST = """\
{
    'name': 'Ideas',
    'version': '1.0',
    'summary': 'Ideas on a board',
    'depends': ['base'],
    'data': [%s],
    'application': True,
    'license': 'LGPL-3',
}
"""


def manifest(*data):
    return MANIFEST % (''.join('\n        %r,' % path for path in data) + ('\n    ' if data else ''))


STAGE = """\
from odoo import fields, models


class IdeaStage(models.Model):
    _name = 'idea.stage'
    _description = 'Idea Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string='Folded in Kanban')
"""

CARD_V1 = """\
from odoo import fields, models


class IdeaCard(models.Model):
    _name = 'idea.card'
    _description = 'Idea'

    name = fields.Char(required=True)
    description = fields.Text()
    priority = fields.Selection([('0', 'Normal'), ('1', 'Important')], default='0')
    color = fields.Integer()
"""

CARD_V2 = CARD_V1.replace("""    color = fields.Integer()
""", """    color = fields.Integer()
    stage_id = fields.Many2one(
        'idea.stage', string='Stage', group_expand='_read_group_expand_full',
        default=lambda self: self.env['idea.stage'].search([], limit=1))
""")

ACCESS = """\
id,name,model_id,group_id/id,operation,domain
access_idea_card_user,idea.card user,idea.card,base.group_user,crud,
access_idea_stage_user,idea.stage user,idea.stage,base.group_user,crud,
"""

STAGES = """\
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">

    <record id="idea_stage_new" model="idea.stage">
        <field name="name">New</field>
        <field name="sequence">10</field>
    </record>

    <record id="idea_stage_progress" model="idea.stage">
        <field name="name">In Progress</field>
        <field name="sequence">20</field>
    </record>

    <record id="idea_stage_done" model="idea.stage">
        <field name="name">Done</field>
        <field name="sequence">30</field>
        <field name="fold" eval="True"/>
    </record>

</odoo>
"""

FORM_V1 = """\
    <record id="idea_card_view_form" model="ir.ui.view">
        <field name="name">idea.card.view.form</field>
        <field name="model">idea.card</field>
        <field name="arch" type="xml">
            <form string="Idea">
                <sheet>
                    <h1><field name="name" placeholder="Your idea"/></h1>
                    <group>
                        <field name="priority" widget="priority"/>
                    </group>
                    <field name="description" placeholder="Tell more..."/>
                </sheet>
            </form>
        </field>
    </record>
"""

FORM_V2 = FORM_V1.replace("""            <form string="Idea">
                <sheet>""", """            <form string="Idea">
                <header>
                    <field name="stage_id" widget="statusbar" options="{'clickable': '1'}"/>
                </header>
                <sheet>""")

LIST_V1 = """\
    <record id="idea_card_view_list" model="ir.ui.view">
        <field name="name">idea.card.view.list</field>
        <field name="model">idea.card</field>
        <field name="arch" type="xml">
            <list string="Ideas">
                <field name="name"/>
                <field name="priority" widget="priority"/>
            </list>
        </field>
    </record>
"""

LIST_V2 = LIST_V1.replace("""                <field name="priority" widget="priority"/>
            </list>""", """                <field name="priority" widget="priority"/>
                <field name="stage_id"/>
            </list>""")

KANBAN = """\
    <record id="idea_card_view_kanban" model="ir.ui.view">
        <field name="name">idea.card.view.kanban</field>
        <field name="model">idea.card</field>
        <field name="arch" type="xml">
            <kanban default_group_by="stage_id" highlight_color="color" on_create="quick_create">
                <field name="color"/>
                <templates>
                    <t t-name="menu">
                        <field name="color" widget="kanban_color_picker"/>
                    </t>
                    <t t-name="card">
                        <field name="name" class="fw-bold fs-5"/>
                        <footer>
                            <field name="priority" widget="priority"/>
                        </footer>
                    </t>
                </templates>
            </kanban>
        </field>
    </record>
"""

STAGE_LIST = """\
    <record id="idea_stage_view_list" model="ir.ui.view">
        <field name="name">idea.stage.view.list</field>
        <field name="model">idea.stage</field>
        <field name="arch" type="xml">
            <list string="Stages" editable="bottom">
                <field name="sequence" widget="handle"/>
                <field name="name"/>
                <field name="fold"/>
            </list>
        </field>
    </record>
"""

ACTIONS = """\
    <record id="idea_card_action" model="ir.actions.act_window">
        <field name="name">Ideas</field>
        <field name="res_model">idea.card</field>
        <field name="view_mode">%s</field>
    </record>

    <record id="idea_stage_action" model="ir.actions.act_window">
        <field name="name">Stages</field>
        <field name="res_model">idea.stage</field>
        <field name="view_mode">list</field>
    </record>

    <menuitem id="idea_root" name="Ideas"
              web_icon="learn_ideas,static/description/icon.png"/>
    <menuitem id="idea_card_menu" name="Ideas" parent="idea_root" action="idea_card_action" sequence="10"/>
    <menuitem id="idea_config_menu" name="Configuration" parent="idea_root" sequence="90"/>
    <menuitem id="idea_stage_menu" name="Stages" parent="idea_config_menu" action="idea_stage_action"/>
"""


def views(*records):
    return '<?xml version="1.0" encoding="utf-8"?>\n<odoo>\n\n' + '\n'.join(records) + '\n</odoo>\n'


DATA_V1 = ('security/ir.access.csv', 'views/idea_views.xml')
DATA_V2 = ('security/ir.access.csv', 'data/idea_stage_data.xml', 'views/idea_views.xml')

COURSE = {
    'key': 'kanban',
    'module': 'learn_ideas',
    'app_name': 'Ideas',
    'main_model': 'idea.card',
    'main_action': 'idea_card_action',
    'name': _lt("Organize with a Kanban board"),
    'summary': _lt("Cards in columns, dragged from stage to stage: stages loaded as data, a link, "
                   "and the Kanban view of Odoo 20, with colors and priority stars."),
    'minutes': 20,
    'level': _lt("Intermediate"),
    'video_url': False,
    'default_icon': 'tasks',
    'challenges': [
        {'key': 'deadline', 'kind': 'field', 'model': 'idea.card', 'label': 'Deadline', 'type': 'date',
         'view': 'kanban', 'title': _lt("A deadline on the cards"),
         'todo': _lt("Add a field labelled Deadline, of type Date, to the ideas, and show it on the cards "
                     "of the board."),
         'hint_code': _lt("A fields.Date in the model, and a field element in the card template of the "
                          "Kanban view. Restart Odoo, then Upgrade."),
         'hint_live': _lt("Settings > Technical > Models: open x_idea_card and add x_deadline. Then "
                          "Technical > Views: add it to the card of the Kanban view.")},
        {'key': 'important', 'kind': 'filter', 'model': 'idea.card', 'label': 'Important',
         'title': _lt("A filter for the important ideas"),
         'todo': _lt("Add a search view to the ideas, with a filter labelled Important: the ideas with a star."),
         'hint_code': _lt("A search view with a filter element, its domain on priority. Upgrade."),
         'hint_live': _lt("Settings > Technical > Views: create a search view for x_idea_card, with the "
                          "filter, its domain on x_priority.")},
    ],
    'steps': [
        {
            'key': 'intro',
            'title': _lt("What we will build"),
            'intro': True,
            'preview': '/om_academy/static/img/kanban_preview.gif',
            'explain': _lt(
                "<p><b>Ideas</b>, an app to move ideas forward: a board with a column per stage, "
                "New, In Progress, Done, and cards you drag from one to the next, with colors "
                "and priority stars.</p>"
                "<p>On the way: data files, a link that groups, and the <b>Kanban view</b> of "
                "Odoo 20.</p>"),
        },
        {
            'key': 'app',
            'title': _lt("Ideas and stages"),
            'explain': _lt(
                "<p>Two models, as in your first app: the <b>ideas</b>, and the <b>stages</b> they "
                "go through. A list and a form for the ideas, a list for the stages under "
                "Configuration.</p>"
                "<ul><li><code>_order = 'sequence, id'</code> sorts the stages by their "
                "sequence: the <code>handle</code> widget lets you drag them in the list;</li>"
                "<li><code>fields.Text</code> holds text of many lines;</li>"
                "<li>the <code>priority</code> widget shows a Selection as stars.</li></ul>"),
            'files': {
                '__manifest__.py': manifest(*DATA_V1),
                '__init__.py': "from . import models\n",
                'models/__init__.py': "from . import idea_stage\nfrom . import idea_card\n",
                'models/idea_stage.py': STAGE,
                'models/idea_card.py': CARD_V1,
                'security/ir.access.csv': ACCESS,
                'views/idea_views.xml': views(FORM_V1, LIST_V1, STAGE_LIST, ACTIONS % 'list,form'),
                ICON_PATH: ICON,
            },
            'live': [
                {'op': 'model', 'model': 'idea.stage', 'string': 'Idea Stage', 'order': 'sequence, id',
                 'fold_name': 'fold', 'fields': [
                     {'name': 'name', 'type': 'char', 'string': 'Name', 'required': True},
                     {'name': 'sequence', 'type': 'integer', 'string': 'Sequence', 'default': 10},
                     {'name': 'fold', 'type': 'boolean', 'string': 'Folded in Kanban'},
                 ]},
                {'op': 'model', 'model': 'idea.card', 'string': 'Idea', 'fields': [
                    {'name': 'name', 'type': 'char', 'string': 'Name', 'required': True},
                    {'name': 'description', 'type': 'text', 'string': 'Description'},
                    {'name': 'priority', 'type': 'selection', 'string': 'Priority', 'default': '0',
                     'selection': [('0', 'Normal'), ('1', 'Important')]},
                    {'name': 'color', 'type': 'integer', 'string': 'Color'},
                ]},
            ],
            'live_note': _lt(
                "Two models, their access rights, views, actions and menus. The order of the "
                "stages is the field <b>Order</b> of <code>ir.model</code>."),
            'code_note': _lt("Create <code>learn_ideas</code> in your addons path, or click <b>Write it "
                             "for me</b>, then <b>Install</b>."),
            'see': 'app',
            'see_text': _lt("Ideas is on the home screen: add an idea, and the stages in Configuration."),
        },
        {
            'key': 'stages',
            'title': _lt("Stages as data"),
            'explain': _lt(
                "<p>An app comes with some records: here the stages. A <b>data file</b> holds them "
                "as XML <code>record</code>s, loaded at install, like views and menus.</p>"
                "<ul><li><code>noupdate=\"1\"</code>: Odoo creates them once and never updates "
                "them again, so the user may rename them;</li>"
                "<li><code>eval=\"True\"</code> gives a Python value: here, Done is folded on "
                "the board.</li></ul>"
                "<p>The data file comes after the access rights and before the views in the "
                "manifest.</p>"),
            'files': {
                '__manifest__.py': manifest(*DATA_V2),
                'data/idea_stage_data.xml': STAGES,
            },
            'live': [],
            'live_note': _lt("Three records of <code>x_idea_stage</code>, as the data file would load them."),
            'code_note': _lt("Click <b>Upgrade</b>: the stages appear in Configuration."),
            'see': 'app',
            'see_text': _lt("Ideas > Configuration > Stages: New, In Progress and Done."),
        },
        {
            'key': 'link',
            'title': _lt("Each idea in a stage"),
            'explain': _lt(
                "<p>A <code>Many2one</code> to the stages, and the <code>statusbar</code> widget in "
                "the header shows where the idea is: click a stage to move it.</p>"
                "<ul><li><code>default=lambda self: ...</code> puts a new idea in the first "
                "stage;</li>"
                "<li><code>group_expand='_read_group_expand_full'</code> shows every stage when "
                "the ideas are grouped by stage, even the empty ones: the columns of the "
                "board.</li></ul>"),
            'files': {
                'models/idea_card.py': CARD_V2,
                'views/idea_views.xml': views(FORM_V2, LIST_V2, STAGE_LIST, ACTIONS % 'list,form'),
            },
            'live': [
                {'op': 'field', 'model': 'idea.card', 'name': 'stage_id', 'type': 'many2one',
                 'relation': 'idea.stage', 'string': 'Stage', 'group_expand': True},
            ],
            'live_note': _lt(
                "The field <code>x_stage_id</code>, with <b>Expand Groups</b> ticked. A field built "
                "in the database cannot default to the first stage: pick it on the idea."),
            'code_note': _lt("Python changed: <b>restart</b> Odoo, then click <b>Upgrade</b>."),
            'see': 'form',
            'see_text': _lt("Open an idea: click the stages of the status bar."),
        },
        {
            'key': 'kanban',
            'title': _lt("The Kanban board"),
            'explain': _lt(
                "<p>A <b>Kanban view</b> shows a card per record. "
                "<code>default_group_by=\"stage_id\"</code> lays them in a column per stage: drag "
                "a card, and Odoo writes its new stage.</p>"
                "<ul><li>the card is the template <code>card</code>: fields, and a "
                "<code>footer</code>;</li>"
                "<li>the template <code>menu</code> opens from the card's three dots: here a "
                "color picker, and <code>highlight_color=\"color\"</code> colors the card;</li>"
                "<li><code>on_create=\"quick_create\"</code>: the + of a column adds a card "
                "there.</li></ul>"
                "<p>The action now opens the board first: <code>kanban,list,form</code>.</p>"),
            'files': {
                'views/idea_views.xml': views(KANBAN, FORM_V2, LIST_V2, STAGE_LIST, ACTIONS % 'kanban,list,form'),
            },
            'live': [],
            'live_note': _lt("A record of <code>ir.ui.view</code> of type kanban, and the action opens it first."),
            'code_note': _lt("Only XML changed: click <b>Upgrade</b>."),
            'see': 'list',
            'see_text': _lt("Open Ideas: drag a card to another column, give it a color and a star."),
        },
        {
            'key': 'finish',
            'title': _lt("Your board is ready"),
            'finish': True,
            'explain': _lt(
                "<p>A board like the ones of CRM and Project: stages as data, a link that groups, "
                "a Kanban view with drag and drop, colors and stars.</p>"
                "<p><b>Export as app</b> gives you the module as a zip.</p>"),
            'files': {},
            'see': 'list',
            'see_text': _lt("Your board."),
        },
    ],
}
