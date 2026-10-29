# The bug hunt: the errors every Odoo developer meets in their first weeks. A
# bug is code, the error Odoo shows, and four reasons: the learner picks the
# one that explains it. Wrong, they try again; right, they read why and how to
# fix it, then hunt the next one. The code and the errors are what Odoo shows,
# so they stay in English; what explains them is translated.
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)


def bug(key, title, path, code, error, options, right, why, fix, hint):
    return {'key': key, 'title': title, 'path': path, 'code': code, 'error': error,
            'options': options, 'right': right, 'why': why, 'fix': fix, 'hint': hint}


BUGS = [
    bug('manifest_comma', _lt("The app that never shows up"), '__manifest__.py', """\
{
    'name': 'Todo',
    'version': '1.0'
    'depends': ['base'],
    'data': ['views/todo_views.xml'],
}""", """\
WARNING odoo.modules.module: Failed to parse the manifest file at
'/opt/addons/todo/__manifest__.py'
SyntaxError: invalid syntax. Perhaps you forgot a comma? (line 3)""",
        [_lt("The module needs 'mail' in its depends"),
         _lt("A comma is missing at the end of the line 'version'"),
         _lt("The version must be a number, not text"),
         _lt("The data file is missing")], 1,
        _lt("The manifest is a Python dictionary: each line ends with a comma. Without it, Python reads "
            "two strings in a row and cannot parse the file, so Odoo skips the module: it is not in Apps."),
        "    'version': '1.0',",
        _lt("Read the line the error points to, and the one before it.")),

    bug('init_import', _lt("The model that does not exist"), 'models/__init__.py', """\
# models/__init__.py
from . import todo_stage

# models/todo_task.py
class TodoTask(models.Model):
    _name = 'todo.task'
    ...""", """\
odoo.tools.convert.ParseError: while parsing views/todo_views.xml:3
Model not found: todo.task

View error context:
{'file': '/opt/addons/todo/views/todo_views.xml', 'line': 3, 'name': 'todo.task.view.form'}""",
        [_lt("The view is written before the model in the file"),
         _lt("The model needs a _description"),
         _lt("models/__init__.py does not import todo_task, so Odoo never loads the class"),
         _lt("The model name must have no dot")], 2,
        _lt("Odoo only knows the Python files it imports. A file of models/ must be imported in "
            "models/__init__.py, and the folder models in the __init__.py of the module."),
        "from . import todo_stage\nfrom . import todo_task",
        _lt("The class is right. Is the file it is in ever read?")),

    bug('view_field', _lt("A field Odoo does not know"), 'views/todo_views.xml', """\
<form string="Task">
    <sheet>
        <field name="name"/>
        <field name="deadline"/>
    </sheet>
</form>

# models/todo_task.py
    name = fields.Char(required=True)
    date_deadline = fields.Date()""", """\
odoo.tools.convert.ParseError: while parsing views/todo_views.xml:4
Field "deadline" does not exist in model "todo.task\"""",
        [_lt("The field in the view is named deadline, in the model date_deadline"),
         _lt("Date fields cannot be shown in a form"),
         _lt("The field must be in a group to be shown"),
         _lt("The view needs a list view first")], 0,
        _lt("A view shows fields by their technical name, the name of the Python attribute. The view "
            "and the model must use the same name: date_deadline."),
        '        <field name="date_deadline"/>',
        _lt("Compare the name in the view with the name in the Python file, letter by letter.")),

    bug('python_restart', _lt("The field is in the file, and still missing"), 'models/todo_task.py', """\
class TodoTask(models.Model):
    _name = 'todo.task'

    name = fields.Char(required=True)
    priority = fields.Selection([('0', 'Normal'), ('1', 'Urgent')])   # just added

# Then: Apps > Todo > Upgrade""", """\
odoo.tools.convert.ParseError: while parsing views/todo_views.xml:5
Field "priority" does not exist in model "todo.task\"""",
        [_lt("Selection fields need a default value"),
         _lt("The Upgrade button deletes new fields"),
         _lt("The values of the selection must be numbers"),
         _lt("Odoo still runs the Python it loaded when it started: restart it, then upgrade")], 3,
        _lt("Python is loaded once, when Odoo starts. After changing a .py file, restart Odoo (or run it "
            "with --dev=reload), then upgrade the module. XML is read again at every upgrade."),
        "./odoo-bin -c odoo.conf -u todo",
        _lt("What reads the Python files, and when?")),

    bug('access_csv', _lt("The access right that finds nothing"), 'security/ir.access.csv', """\
id,name,model_id,group_id/id,operation,domain
access_todo_task_user,todo.task user,todo.task,base.group_user,crud,""", """\
odoo.tools.convert.ParseError: while parsing security/ir.access.csv:2
No matching record found for external id 'todo.task' in field 'Model'""",
        [_lt("The operation crud is not valid"),
         _lt("The group base.group_user does not exist"),
         _lt("model_id needs the external id of the model: model_todo_task"),
         _lt("The file must be named ir.model.access.csv")], 2,
        _lt("model_id links to a record of ir.model, by its external id: model_ and the model name with "
            "underscores. todo.task becomes model_todo_task."),
        "access_todo_task_user,todo.task user,model_todo_task,base.group_user,crud,",
        _lt("A link in a data file is an external id. What is the one of a model?")),

    bug('menu_order', _lt("The menu before its action"), 'views/todo_views.xml', """\
<odoo>
    <menuitem id="todo_menu" name="Tasks" parent="todo_root" action="todo_task_action"/>

    <record id="todo_task_action" model="ir.actions.act_window">
        <field name="name">Tasks</field>
        <field name="res_model">todo.task</field>
    </record>
</odoo>""", """\
odoo.tools.convert.ParseError: while parsing views/todo_views.xml:2
External ID not found in the system: todo.todo_task_action""",
        [_lt("A menu cannot have an action"),
         _lt("Odoo reads the file from top to bottom: the action must come before the menu that opens it"),
         _lt("The action needs a view_mode"),
         _lt("The menu needs a sequence")], 1,
        _lt("Data files are loaded in order, record by record: a record can only refer to one loaded "
            "before it. Put the action first, then the menu. The same goes for the files of the manifest."),
        "<record id=\"todo_task_action\" .../>\n<menuitem id=\"todo_menu\" ... action=\"todo_task_action\"/>",
        _lt("The id exists in the file. But does it exist yet, when Odoo reads that line?")),

    bug('xml_tag', _lt("The view that is not XML"), 'views/todo_views.xml', """\
<form string="Task">
    <sheet>
        <group>
            <field name="name"/>
            <field name="date_deadline"/>
        </sheet>
    </group>
</form>""", """\
lxml.etree.XMLSyntaxError: Opening and ending tag mismatch: group line 3 and sheet, line 6, column 17""",
        [_lt("A form can have only one group"),
         _lt("The tags close in the wrong order: group must close before sheet"),
         _lt("The field date_deadline needs a widget"),
         _lt("The view needs an id")], 1,
        _lt("XML tags close in the reverse order they open: the last opened, the first closed. Here "
            "</group> must come before </sheet>. Indenting the code well makes it easy to see."),
        "        </group>\n    </sheet>",
        _lt("Follow the lines the error names: which tag opened last?")),

    bug('button_method', _lt("The button with no method"), 'views/todo_views.xml', """\
<header>
    <button name="action_done" string="Done" type="object"/>
</header>

# models/todo_task.py
    def action_finish(self):
        self.state = 'done'""", """\
odoo.tools.convert.ParseError: while parsing views/todo_views.xml:12
action_done is not a valid action on todo.task""",
        [_lt("The button calls action_done, but the method is named action_finish"),
         _lt("Buttons only work in the list view"),
         _lt("type must be action, not object"),
         _lt("A method of a button must return True")], 0,
        _lt("A button of type object calls the method of the model named in name. Odoo checks it "
            "exists when it loads the view: the names must match."),
        '    <button name="action_finish" string="Done" type="object"/>',
        _lt("What does name mean on a button of type object?")),

    bug('singleton', _lt("Expected singleton"), 'models/todo_task.py', """\
def action_done(self):
    if self.state == 'done':
        raise UserError("Already done.")
    self.state = 'done'

# The user selects 3 tasks in the list, then Actions > Done""", """\
ValueError: Expected singleton: todo.task(4, 7, 9)""",
        [_lt("The method must be decorated with @api.model"),
         _lt("UserError cannot be raised from a button"),
         _lt("state must be a Char field"),
         _lt("self holds 3 records: self.state only works on one. Loop over self")], 3,
        _lt("self is a recordset: it may hold many records. Reading a field on it needs exactly one. "
            "Loop: for task in self: ..., or call self.ensure_one() when the method is for one record only."),
        "for task in self:\n    if task.state == 'done':\n        raise UserError(\"Already done.\")\n    task.state = 'done'",
        _lt("How many records are in self, when the user selects three?")),

    bug('compute_assign', _lt("A computed field left empty"), 'models/todo_task.py', """\
late = fields.Boolean(compute='_compute_late')

@api.depends('date_deadline')
def _compute_late(self):
    for task in self:
        if task.date_deadline:
            task.late = task.date_deadline < fields.Date.today()""", """\
ValueError: Compute method failed to assign todo.task(12,).late""",
        [_lt("Boolean fields cannot be computed"),
         _lt("A task without a deadline gets no value: every record must get one"),
         _lt("@api.depends must list late too"),
         _lt("fields.Date.today() is not allowed in a compute")], 1,
        _lt("A compute method must give a value to the field on every record of self, in every case. "
            "Here a task without a deadline gets none: add an else, or write the value in one line."),
        "        task.late = bool(task.date_deadline) and task.date_deadline < fields.Date.today()",
        _lt("Follow the loop for a task with no deadline: what does it set?")),

    bug('depends', _lt("The total that never moves"), 'models/todo_task.py', """\
hours = fields.Float()
rate = fields.Float()
cost = fields.Float(compute='_compute_cost', store=True)

@api.depends('hours')
def _compute_cost(self):
    for task in self:
        task.cost = task.hours * task.rate""", """\
No error at all. But change the rate of a task: its cost stays the same.
Change its hours: the cost is right again.""",
        [_lt("A stored field cannot be computed"),
         _lt("Float fields need digits"),
         _lt("@api.depends lists hours only: Odoo does not recompute when rate changes"),
         _lt("The compute method must return the value")], 2,
        _lt("A stored computed field is recomputed only when a field of @api.depends changes. List every "
            "field the compute reads: @api.depends('hours', 'rate')."),
        "@api.depends('hours', 'rate')",
        _lt("When does Odoo run the compute of a stored field?")),

    bug('comodel', _lt("A link to nowhere"), 'models/todo_task.py', """\
class TodoTask(models.Model):
    _name = 'todo.task'

    stage_id = fields.Many2one('todo.stages', string='Stage')

class TodoStage(models.Model):
    _name = 'todo.stage'""", """\
TypeError: Field todo.task.stage_id with unknown comodel_name 'todo.stages'""",
        [_lt("A Many2one needs a One2many on the other side"),
         _lt("string must be the model's name"),
         _lt("Stages must be a Selection field"),
         _lt("The Many2one points to todo.stages, but the model is todo.stage")], 3,
        _lt("The first argument of a Many2one is the _name of the model it links to, exactly. A typo, "
            "or a model of a module not in the depends, and Odoo cannot build the field."),
        "    stage_id = fields.Many2one('todo.stage', string='Stage')",
        _lt("Compare the model the field links to with the _name of the other class.")),

    bug('no_access', _lt("The menu nobody can open"), 'security/ir.access.csv', """\
# __manifest__.py
    'data': ['views/todo_views.xml'],

# No security/ir.access.csv in the module""", """\
WARNING odoo.modules.loading: The models ['todo.task'] have no access rules in module todo,
consider adding some.

Then, opening Tasks: You are not allowed to access 'Task' (todo.task) records.""",
        [_lt("The model has no access right: no user may read it, so add an ir.access.csv"),
         _lt("The menu needs the group of the administrators"),
         _lt("The user must log out and in again"),
         _lt("The action needs a domain")], 0,
        _lt("A new model is closed to everybody until an access right opens it. Add "
            "security/ir.access.csv, and list it in the data of the manifest, before the views."),
        "access_todo_task_user,todo.task user,model_todo_task,base.group_user,crud,",
        _lt("The warning at install tells it. Who may read todo.task?")),

    bug('owl_template', _lt("The component with no template"), 'static/src/todo_board.js', """\
// static/src/todo_board.js
export class TodoBoard extends Component {
    static template = "todo.Board";
}

<!-- static/src/todo_board.xml -->
<templates>
    <t t-name="todo.TodoBoard">
        <h1>My tasks</h1>
    </t>
</templates>""", """\
UncaughtPromiseError > OwlError
Missing template: "todo.Board" (for component "TodoBoard")""",
        [_lt("Components need a setup() method"),
         _lt("The template is named todo.TodoBoard, the component asks for todo.Board"),
         _lt("The XML file must be in views/"),
         _lt("OWL templates must start with a div")], 1,
        _lt("static template names the template the component renders, and t-name gives it: they must "
            "be the same. The XML file must also be in the assets of the manifest, like the JS."),
        '    static template = "todo.TodoBoard";',
        _lt("Two names should be one. Which ones?")),
]

BUGS_BY_KEY = {bug['key']: bug for bug in BUGS}
