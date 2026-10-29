# Explain this line: a note in plain words for the lines of Odoo code the
# courses show. A glossary of patterns rather than notes per course, so that
# every course, on every subject, gets them. The first pattern matching a line
# gives its note: the more precise ones come first.
import re

from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

NOTES = [
    # the manifest
    (r"^\s*'name':", _lt("The name of your app, as Apps shows it.")),
    (r"^\s*'version':", _lt("The version of your module: raise it when you change it, Odoo shows it in Apps.")),
    (r"^\s*'author':", _lt("You! The author of the module, shown in Apps.")),
    (r"^\s*'summary':", _lt("One line about the app, under its name in Apps.")),
    (r"^\s*'depends':", _lt("The modules yours builds upon: Odoo installs them first, and loads them before yours.")),
    (r"^\s*'data':", _lt("The data files Odoo loads when it installs or upgrades the module, in this order.")),
    (r"^\s*'application': True", _lt("Makes the module an app: in Apps, under the Apps filter.")),
    (r"^\s*'license':", _lt("The license of your code. LGPL-3 is the one of Odoo Community.")),
    # Python
    (r"^from odoo import", _lt("Brings in Odoo's tools: models to declare a model, fields for its fields, api for decorators.")),
    (r"^from \. import", _lt("Loads a Python file of this folder: without this line, Odoo never reads it.")),
    (r"^class \w+\(models\.Model\)", _lt("A model: a Python class Odoo turns into a table of the database.")),
    (r"^\s*_name = ", _lt("The technical name of the model. Its table is named after it: dots become underscores.")),
    (r"^\s*_description = ", _lt("A name for people: Odoo shows it in its screens and messages.")),
    (r"^\s*_inherit = \['mail\.thread'\]", _lt("Adds the behaviour of mail.thread to your model: messages, followers, the chatter.")),
    (r"^\s*_inherit = '", _lt("Without a _name, this adds to an existing model instead of creating one.")),
    (r"tracking=True", _lt("Each change of this field is written in the chatter: who, when, from what to what.")),
    (r"compute='", _lt("Not typed in: the method named here computes it. Not stored, it is computed when read.")),
    (r"fields\.Many2one\(", _lt("A link to one record of another model, stored as its id: the name ends in _id.")),
    (r"fields\.Selection\(", _lt("A choice among fixed values: each a pair (value stored, label shown).")),
    (r"fields\.Char\(", _lt("A text field on one line.")),
    (r"fields\.Date\(", _lt("A date, without the time.")),
    (r"fields\.Integer\(", _lt("A whole number.")),
    (r"fields\.Boolean\(", _lt("Yes or no: shown as a checkbox.")),
    (r"default=lambda", _lt("A new record starts with this: here computed when the record is created.")),
    (r"default=", _lt("The value a new record starts with.")),
    (r"required=True", _lt("Must be filled: Odoo refuses to save the record without it.")),
    (r"^\s*\[\('|^\s*\('\w+', '", _lt("The values of the selection: the value stored, then the label shown.")),
    (r"string='", _lt("The label of the field in the screens. Without it, Odoo makes one from the name.")),
    (r"@api\.depends\(", _lt("The fields the computation reads: Odoo recomputes when one of them changes.")),
    (r"def _compute_", _lt("Computes the field for each record of self: every record must get a value.")),
    (r"def action_", _lt("A method a button calls (a button of type object): self is the records shown.")),
    (r"^\s*for \w+ in self:", _lt("self holds one record or many: the loop treats each.")),
    (r"context_today\(", _lt("Today, in the timezone of the user.")),
    (r"\.write\(\{", _lt("Changes fields of the records, all in one go.")),
    (r"^\s*if .*:$", _lt("Only when this is true.")),
    (r"^\s*else:$", _lt("Otherwise.")),
    (r"\.days$", _lt("The number of days between the two dates.")),
    # XML
    (r"^<\?xml", _lt("Every data file of Odoo is XML.")),
    (r"^<odoo>|^</odoo>", _lt("Wraps the records of the file.")),
    (r'<record id="\w+" model="ir\.ui\.view"', _lt("A view: a record of ir.ui.view. id is its external id, to find it again.")),
    (r'<record id="\w+" model="ir\.actions\.act_window"', _lt("A window action: what to open when a menu is clicked.")),
    (r'<record id="\w+" model="res\.groups\.privilege"', _lt("A privilege: one choice on the user form, holding the groups of the app.")),
    (r'<record id="\w+" model="res\.groups"', _lt("A group: a role. Users get rights through their groups.")),
    (r'<record id=', _lt("A record Odoo creates, or updates if it exists: id is its external id.")),
    (r'<field name="name">', _lt("The name of the record. For a view, Odoo's guidelines say model.view.type.")),
    (r'<field name="model">', _lt("The model the view shows.")),
    (r'<field name="inherit_id"', _lt("The view this one changes: Odoo merges both, yours applied on top.")),
    (r'<field name="arch" type="xml">', _lt("The layout of the view itself, in XML.")),
    (r'<field name="res_model">', _lt("The model the action opens.")),
    (r'<field name="view_mode">', _lt("The views the action offers, the first one shown first.")),
    (r'<field name="domain">', _lt("Only the records matching this condition.")),
    (r'<field name="privilege_id"', _lt("The privilege the group belongs to.")),
    (r'<field name="implied_ids"', _lt("Whoever is in this group is in those too: a manager is a user as well.")),
    (r'<field name="user_ids"', _lt("Puts these users in the group.")),
    (r'<field name="sequence">', _lt("The order: lower first.")),
    (r"<xpath ", _lt("Finds a place in the view inherited, and changes it there.")),
    (r'position="after"', _lt("Puts what follows right after the element found.")),
    (r"<form ", _lt("A form view: one record at a time.")),
    (r"<list ", _lt("A list view: one record per line. Older versions called it tree.")),
    (r"<search ", _lt("The search view: what the search bar offers.")),
    (r"<header>", _lt("The bar above the sheet: buttons, and the status.")),
    (r"<sheet>", _lt("The sheet, like a page, holding the fields.")),
    (r"<group>", _lt("Lays the fields out with their labels.")),
    (r"<chatter", _lt("The chatter: messages and history, next to the form.")),
    (r'widget="statusbar"', _lt("Shows the status as a bar of steps.")),
    (r"<button ", _lt("A button. type object calls the method of the model named in name.")),
    (r'invisible="', _lt("Hidden while this condition is true, checked as the user works.")),
    (r'readonly="', _lt("Locked while this condition is true.")),
    (r'required="', _lt("Mandatory while this condition is true.")),
    (r'groups="', _lt("Only the users of this group see it.")),
    (r"<filter .*group_by", _lt("A group-by of the search bar.")),
    (r"<filter ", _lt("A filter of the search bar: the domain picks the records.")),
    (r'context="\{\'group_by\'', _lt("Groups the records by this field.")),
    (r"domain=\"\[", _lt("A domain: a condition, as a list of (field, operator, value).")),
    (r"<menuitem .*parent=", _lt("A menu under another one: clicking it runs its action.")),
    (r"<menuitem ", _lt("A menu without a parent: an app on the home screen.")),
    (r'web_icon=', _lt("The icon of the app on the home screen: module,path of the image.")),
    (r"<field name=", _lt("A field shown in the view.")),
    # access rights
    (r"^id,name,model_id", _lt("The columns of an access right: its id, name, model, group, the operations, and a domain.")),
    (r",crud,|,cru,|,r,", _lt("The operations allowed: c create, r read, u update, d delete. A domain at the end limits the records.")),
]

PATTERNS = [(re.compile(pattern), note) for pattern, note in NOTES]


def line_note(text):
    """ The note of a line of code, or None. """
    for pattern, note in PATTERNS:
        if pattern.search(text):
            return note
    return None
