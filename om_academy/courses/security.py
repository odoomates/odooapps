# Course 3: secure an app, the Odoo 20 way. A To-Do app, then groups under a
# privilege, access rights per group, and a domain on an access right so that
# a user sees only their own tasks (Odoo 20 has no more record rules).
from odoo.tools.translate import LazyTranslate

from ..models.course_files import ICON, ICON_PATH

_lt = LazyTranslate(__name__)

MANIFEST = """\
{
    'name': 'To-Do',
    'version': '1.0',
    'summary': 'Tasks, secured',
    'depends': ['base'],
    'data': [%s],
    'application': True,
    'license': 'LGPL-3',
}
"""


def manifest(*data):
    return MANIFEST % (''.join('\n        %r,' % path for path in data) + ('\n    ' if data else ''))


TASK = """\
from odoo import fields, models


class TodoTask(models.Model):
    _name = 'todo.task'
    _description = 'Task'

    name = fields.Char(required=True)
    user_id = fields.Many2one('res.users', string='Assigned To', default=lambda self: self.env.user)
    is_done = fields.Boolean(string='Done')
"""

VIEWS = """\
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="todo_task_view_list" model="ir.ui.view">
        <field name="name">todo.task.view.list</field>
        <field name="model">todo.task</field>
        <field name="arch" type="xml">
            <list string="Tasks" editable="bottom">
                <field name="is_done"/>
                <field name="name"/>
                <field name="user_id"/>
            </list>
        </field>
    </record>

    <record id="todo_task_action" model="ir.actions.act_window">
        <field name="name">Tasks</field>
        <field name="res_model">todo.task</field>
        <field name="view_mode">list</field>
    </record>

    <menuitem id="todo_root" name="To-Do"
              web_icon="learn_todo,static/description/icon.png"/>
    <menuitem id="todo_task_menu" name="Tasks" parent="todo_root" action="todo_task_action"/>

</odoo>
"""

# a menu for the managers only: the tasks done, by everyone
VIEWS_MENUS = VIEWS.replace("""    <menuitem id="todo_root" name="To-Do"
              web_icon="learn_todo,static/description/icon.png"/>
    <menuitem id="todo_task_menu" name="Tasks" parent="todo_root" action="todo_task_action"/>""", """    <record id="todo_task_action_done" model="ir.actions.act_window">
        <field name="name">Done Tasks</field>
        <field name="res_model">todo.task</field>
        <field name="view_mode">list</field>
        <field name="domain">[('is_done', '=', True)]</field>
    </record>

    <menuitem id="todo_root" name="To-Do"
              web_icon="learn_todo,static/description/icon.png"/>
    <menuitem id="todo_task_menu" name="Tasks" parent="todo_root" action="todo_task_action"
              sequence="10"/>
    <menuitem id="todo_task_menu_done" name="Done Tasks" parent="todo_root"
              action="todo_task_action_done" sequence="20" groups="learn_todo_group_manager"/>""")

# a column for the managers only: whom a task is assigned to
VIEWS_FIELDS = VIEWS_MENUS.replace("""                <field name="user_id"/>""",
                                   """                <field name="user_id" groups="learn_todo_group_manager"/>""")

GROUPS = """\
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="privilege_todo" model="res.groups.privilege">
        <field name="name">To-Do</field>
    </record>

    <record id="learn_todo_group_user" model="res.groups">
        <field name="name">User</field>
        <field name="privilege_id" ref="privilege_todo"/>
        <field name="sequence">10</field>
    </record>

    <record id="learn_todo_group_manager" model="res.groups">
        <field name="name">Manager</field>
        <field name="privilege_id" ref="privilege_todo"/>
        <field name="sequence">20</field>
        <field name="implied_ids" eval="[(4, ref('learn_todo_group_user'))]"/>
        <field name="user_ids" eval="[(4, ref('base.user_admin'))]"/>
    </record>

</odoo>
"""

ACCESS_OPEN = """\
id,name,model_id,group_id/id,operation,domain
access_todo_task_all,todo.task all,todo.task,base.group_user,crud,
"""

ACCESS_GROUPS = """\
id,name,model_id,group_id/id,operation,domain
access_todo_task_user,todo.task user,todo.task,learn_todo_group_user,cru,
access_todo_task_manager,todo.task manager,todo.task,learn_todo_group_manager,crud,
"""

ACCESS_OWN = """\
id,name,model_id,group_id/id,operation,domain
access_todo_task_user,todo.task user,todo.task,learn_todo_group_user,cru,"[('user_id', '=', user.id)]"
access_todo_task_manager,todo.task manager,todo.task,learn_todo_group_manager,crud,
"""

COURSE = {
    'key': 'security',
    'app_name': 'To-Do',
    'challenges': [
        {'key': 'delete', 'kind': 'access', 'model': 'todo.task', 'group': 'learn_todo_group_user',
         'operation': 'd', 'what': _lt("delete"), 'title': _lt("Let users delete"),
         'todo': _lt("Let the To-Do users delete their own tasks too."),
         'hint_code': _lt("One letter in the users' line of ir.access.csv. Upgrade."),
         'hint_live': _lt("Developer mode, Settings > Technical > Security > Access: open the access right of "
                          "the users on x_todo_task, and allow the deletion.")},
        {'key': 'deadline', 'kind': 'field', 'model': 'todo.task', 'label': 'Deadline', 'type': 'date',
         'view': 'list', 'title': _lt("A deadline"),
         'todo': _lt("Add a field labelled Deadline, of type Date, to the tasks, and show it in the list."),
         'hint_code': _lt("A fields.Date in the model, a field element in the list view. Restart, Upgrade."),
         'hint_live': _lt("Settings > Technical > Models: open x_todo_task and add x_deadline. Then Technical > "
                          "Views: add it to the list view.")},
    ],
    'module': 'learn_todo',
    'main_model': 'todo.task',
    'main_action': 'todo_task_action',
    'name': _lt("Secure an app, the Odoo 20 way"),
    'summary': _lt("Groups, access rights per group, and a domain so that each user sees only "
                   "their own records: the security of Odoo 20, which has no more record rules."),
    'minutes': 15,
    'level': _lt("Intermediate"),
    'video_url': False,
    'steps': [
        {
            'key': 'intro',
            'title': _lt("What we will build"),
            'intro': True,
            'preview': '/om_academy/static/img/security_preview.gif',
            'explain': _lt(
                "<p>A small <b>To-Do</b> app, then its security: <b>users</b> who manage their "
                "own tasks and cannot delete them, and <b>managers</b> who see and do "
                "everything.</p>"
                "<p>Odoo 20 changed security: there are no record rules any more. An access "
                "right can carry a <b>domain</b>, the records it opens. This course shows the "
                "new way.</p>"),
        },
        {
            'key': 'app',
            'title': _lt("The starting app"),
            'explain': _lt(
                "<p>Everything of the first course in one step: a model of tasks, an access "
                "right for every internal user, a list, an action and a menu. "
                "<code>default=lambda self: self.env.user</code> assigns a new task to whoever "
                "creates it.</p>"),
            'files': {
                '__manifest__.py': manifest('security/ir.access.csv', 'views/todo_views.xml'),
                '__init__.py': "from . import models\n",
                'models/__init__.py': "from . import todo_task\n",
                'models/todo_task.py': TASK,
                'security/ir.access.csv': ACCESS_OPEN,
                'views/todo_views.xml': VIEWS,
                ICON_PATH: ICON,
            },
            'live': [{'op': 'model', 'model': 'todo.task', 'string': 'Task', 'fields': [
                {'name': 'name', 'type': 'char', 'string': 'Name', 'required': True},
                {'name': 'user_id', 'type': 'many2one', 'relation': 'res.users', 'string': 'Assigned To'},
                {'name': 'is_done', 'type': 'boolean', 'string': 'Done'},
            ]}],
            'live_note': _lt(
                "The model, its access right, the list, the action and the menus, all at once, "
                "and your module <b>To-Do</b> in <b>Apps</b>, with your name and your icon. A "
                "field created in the database cannot default to the current user: pick the "
                "user yourself."),
            'code_note': _lt(
                "Create <code>learn_todo</code> in your addons path, or click <b>Write it for "
                "me</b>. Then in <b>Apps</b>, <b>Update Apps List</b> (shown in developer mode) and "
                "search <i>To-Do</i>: your module, with your name and your icon. Install it there, "
                "or click <b>Install</b> here, which does both."),
            'see': 'list',
            'see_text': _lt("To-Do is on the home screen: add a few tasks."),
        },
        {
            'key': 'groups',
            'title': _lt("Groups under a privilege"),
            'explain': _lt(
                "<p>A <b>group</b> is a role. Users get rights through their groups, and a user "
                "has the rights of all their groups added up. In Odoo 20, the groups of an app "
                "belong to a <b>privilege</b> (<code>res.groups.privilege</code>), shown as one "
                "choice on the user form: To-Do: <i>User</i> or <i>Manager</i>.</p>"
                "<ul><li><code>implied_ids</code>: every Manager is a User too, so a manager "
                "gets what users get, and more;</li>"
                "<li><code>user_ids</code> puts users in the group from the module: here the "
                "administrator, so that you keep your access at the next steps;</li>"
                "<li>everyone else gets a group on their user form, in "
                "<b>Settings &gt; Users</b>.</li></ul>"
                "<p>Odoo's coding guidelines name a group <code>&lt;module&gt;_group_&lt;role&gt;</code>, "
                "in a file <code>security/&lt;module&gt;_groups.xml</code>.</p>"
                "<p>Groups then open what each role sees: the <b>access rights</b> of models (next "
                "step), the <b>records</b> (a domain), the <b>menus</b> and the <b>parts of a "
                "view</b>, at the last steps.</p>"),
            'files': {
                '__manifest__.py': manifest('security/learn_todo_groups.xml', 'security/ir.access.csv',
                                            'views/todo_views.xml'),
                'security/learn_todo_groups.xml': GROUPS,
            },
            'live': [],
            'live_note': _lt("A record of <code>res.groups.privilege</code> and two of "
                             "<code>res.groups</code>, the administrator in the managers."),
            'code_note': _lt("The groups come <b>before</b> the access rights in the manifest: "
                             "the CSV file will name them. Then click <b>Upgrade</b>."),
            'see': 'model_access',
            'see_text': _lt("Settings > Users: the To-Do choice on a user's form."),
        },
        {
            'key': 'access',
            'title': _lt("Access rights per group"),
            'explain': _lt(
                "<p>The single right for everyone gives way to one right per group. "
                "<code>cru</code> lets a user create, read and update, but not delete; "
                "<code>crud</code> lets a manager do all four. Someone in neither group has "
                "no access at all.</p>"),
            'files': {'security/ir.access.csv': ACCESS_GROUPS},
            'live': [],
            'live_note': _lt("The access right for everyone is gone; one per group replaces it."),
            'code_note': _lt("Click <b>Upgrade</b>: the line removed from the CSV is removed "
                             "from the database too."),
            'see': 'model_access',
            'see_text': _lt("The access rights of the model, per group."),
        },
        {
            'key': 'own',
            'title': _lt("Their own tasks only: a domain"),
            'explain': _lt(
                "<p>A <b>domain</b> on an access right limits it to some records: "
                "<code>[('user_id', '=', user.id)]</code> opens to a user only the tasks "
                "assigned to them. The managers' right has no domain: they see them all.</p>"
                "<p>Before Odoo 20 this was a <b>record rule</b> (<code>ir.rule</code>). In "
                "Odoo 20 it is the last column of <code>ir.access.csv</code>.</p>"),
            'files': {'security/ir.access.csv': ACCESS_OWN},
            'live': [],
            'live_note': _lt("The users' access right now carries a domain. Odoo checks it on "
                             "every read, write and search."),
            'code_note': _lt("Click <b>Upgrade</b>."),
            'see': 'model_access',
            'see_text': _lt("Make a user a To-Do User: they see only their own tasks."),
        },
        {
            'key': 'menus',
            'title': _lt("A menu for managers only"),
            'explain': _lt(
                "<p><code>groups=\"learn_todo_group_manager\"</code> on a <b>menu</b> shows it "
                "to the managers only: the others do not see it at all. Here: <b>Done Tasks</b>, "
                "a second action on the same model, whose <code>domain</code> keeps the tasks "
                "done.</p>"
                "<p>Hiding a menu is no security on its own: what a user may read is decided by "
                "the access rights. A menu with groups is about a clean screen for each "
                "role.</p>"),
            'files': {'views/todo_views.xml': VIEWS_MENUS},
            'live': [],
            'live_note': _lt("The menu's <b>Groups</b> (<code>group_ids</code> of "
                             "<code>ir.ui.menu</code>) hold the Manager group."),
            'code_note': _lt("Only XML changed: click <b>Upgrade</b>."),
            'see': 'list',
            'see_text': _lt("You, a manager, see Done Tasks; a To-Do User does not."),
        },
        {
            'key': 'fields',
            'title': _lt("Parts of a view for managers only"),
            'explain': _lt(
                "<p><code>groups</code> works on any part of a view: a <b>field</b>, a "
                "<b>button</b>, a page, a filter. Odoo removes it from the view for whoever is "
                "not in the group. A user sees only their own tasks: the <b>Assigned To</b> "
                "column tells them nothing, so it is for managers only.</p>"
                "<p>A whole view can have groups too (<code>group_ids</code> of the view): it then "
                "applies only to them.</p>"),
            'files': {'views/todo_views.xml': VIEWS_FIELDS},
            'live': [],
            'live_note': _lt("The list's <code>arch</code> has <code>groups</code> on the field."),
            'code_note': _lt("Only XML changed: click <b>Upgrade</b>."),
            'see': 'list',
            'see_text': _lt("A To-Do User's list has no Assigned To column."),
        },
        {
            'key': 'finish',
            'title': _lt("Your app is secure"),
            'finish': True,
            'explain': _lt(
                "<p>Two groups, an access right each, a domain, a menu and a column for the "
                "managers: who does what, on which records, and who sees what, the way Odoo 20 "
                "does it.</p>"
                "<p><b>Export as app</b> gives you the module as a zip.</p>"),
            'files': {},
            'see': 'list',
            'see_text': _lt("Your tasks."),
        },
    ],
}
