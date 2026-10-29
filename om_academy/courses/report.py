# Course: print a PDF report. A contact card printed from any contact, the
# way Odoo makes its invoices and quotations: a report record, in the Print
# menu, rendering a QWeb template in the layout of the company.
from odoo.tools.translate import LazyTranslate

from ..models.course_files import ICON, ICON_PATH

_lt = LazyTranslate(__name__)

MANIFEST = """\
{
    'name': 'Contact Card',
    'version': '1.0',
    'summary': 'A printable card for your contacts',
    'depends': ['base', 'web'],
    'data': [%s],
    'license': 'LGPL-3',
}
"""


def manifest(*data):
    return MANIFEST % (''.join('\n        %r,' % path for path in data) + ('\n    ' if data else ''))


ACTION = """\
    <record id="action_report_contact_card" model="ir.actions.report">
        <field name="name">Contact Card</field>
        <field name="model">res.partner</field>
        <field name="report_type">qweb-pdf</field>
        <field name="report_name">learn_report.report_contact_card</field>
        <field name="print_report_name">'Card - %s' % object.name</field>
        <field name="binding_model_id" ref="base.model_res_partner"/>
        <field name="binding_type">report</field>
    </record>
"""

PAPER = """\
    <record id="paperformat_contact_card" model="report.paperformat">
        <field name="name">Contact Card</field>
        <field name="format">A5</field>
        <field name="orientation">Landscape</field>
        <field name="margin_top">40</field>
        <field name="margin_bottom">20</field>
        <field name="margin_left">10</field>
        <field name="margin_right">10</field>
        <field name="header_spacing">35</field>
    </record>

"""

ACTION_PAPER = ACTION.replace("""        <field name="binding_type">report</field>""", """        <field name="binding_type">report</field>
        <field name="paperformat_id" ref="paperformat_contact_card"/>""")


def reports(*records):
    return '<?xml version="1.0" encoding="utf-8"?>\n<odoo>\n\n' + ''.join(records) + '\n</odoo>\n'


TEMPLATE_V1 = """\
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <template id="report_contact_card">
        <t t-call="web.html_container">
            <t t-foreach="docs" t-as="doc">
                <t t-call="web.external_layout">
                    <div class="page">
                        <h2 t-field="doc.name"/>
                    </div>
                </t>
            </t>
        </t>
    </template>

</odoo>
"""

TEMPLATE_V2 = TEMPLATE_V1.replace("""                        <h2 t-field="doc.name"/>
""", """                        <h2 t-field="doc.name"/>
                        <div t-out="doc"
                             t-options='{"widget": "contact", "fields": ["address", "phone", "email"]}'/>
                        <p t-if="doc.website">Website: <span t-field="doc.website"/></p>
                        <t t-if="doc.child_ids">
                            <h4 class="mt-4">Contacts</h4>
                            <table class="table table-sm">
                                <thead>
                                    <tr><th>Name</th><th>Email</th><th>Phone</th></tr>
                                </thead>
                                <tbody>
                                    <tr t-foreach="doc.child_ids" t-as="child">
                                        <td t-out="child.name"/>
                                        <td t-out="child.email"/>
                                        <td t-out="child.phone"/>
                                    </tr>
                                </tbody>
                            </table>
                        </t>
""")

DATA = ('report/contact_card_reports.xml', 'report/contact_card_templates.xml')

COURSE = {
    'key': 'report',
    'module': 'learn_report',
    'app_name': 'Contact Card',
    'main_model': 'res.partner',
    'main_action': 'base.action_partner_form',
    'name': _lt("Print a PDF report"),
    'summary': _lt("A contact card printed from any contact, as Odoo prints its invoices: a report in "
                   "the Print menu, a QWeb template, the company's layout, a paper format."),
    'minutes': 15,
    'level': _lt("Intermediate"),
    'video_url': False,
    'default_icon': 'users',
    'challenges': [
        {'key': 'second', 'kind': 'report', 'model': 'res.partner', 'label': 'Contact Badge',
         'title': _lt("A second report"),
         'todo': _lt("Add a second report to the contacts, named Contact Badge, in the Print menu."),
         'hint_code': _lt("One more ir.actions.report record, and its template. Upgrade."),
         'hint_live': _lt("Settings > Technical > Reports: create a report named Contact Badge on res.partner, "
                          "of type PDF, with the template of your card, then Add in the Print menu.")},
    ],
    'steps': [
        {
            'key': 'intro',
            'title': _lt("What we will build"),
            'intro': True,
            'preview': '/om_academy/static/img/report_preview.gif',
            'explain': _lt(
                "<p>A <b>Contact Card</b>: open any contact, click <b>Print</b>, and get a PDF with "
                "the name, the address, the website and the people of the company, in the "
                "layout of your company.</p>"
                "<p>Every PDF of Odoo, invoices and quotations included, is made this way: a "
                "<b>report</b> record and a <b>QWeb template</b>.</p>"),
        },
        {
            'key': 'skeleton',
            'title': _lt("The module skeleton"),
            'explain': _lt(
                "<p>A module without a model: it adds a report to the contacts. It depends on "
                "<code>web</code>, which holds the layouts of the reports.</p>"),
            'files': {'__manifest__.py': manifest(), '__init__.py': '', ICON_PATH: ICON},
            'live': [],
            'live_note': _lt(
                "Your module <b>Contact Card</b> is in <b>Apps</b>, with your name and your icon."),
            'code_note': _lt(
                "Create the folder <code>learn_report</code> in your addons path, or click <b>Write it "
                "for me</b>. Then in Apps, <b>Update Apps List</b>, or click <b>Install</b> here."),
            'see': 'module',
            'see_text': _lt("Apps: your module, with your name and your icon."),
        },
        {
            'key': 'action',
            'title': _lt("A report in the Print menu"),
            'explain': _lt(
                "<p>A <b>report</b> is a record of <code>ir.actions.report</code>: the model it "
                "prints, the type <code>qweb-pdf</code>, and <code>report_name</code>, the template "
                "to render. <code>binding_model_id</code> puts it in the <b>Print</b> menu of the "
                "contacts; <code>print_report_name</code> names the file.</p>"
                "<p>The template loops on <code>docs</code>, the records printed, and calls "
                "<code>web.external_layout</code>: the header and footer of your company. "
                "<code>t-field</code> shows a field as Odoo formats it.</p>"
                "<p>Odoo's guidelines put the report in <code>&lt;name&gt;_reports.xml</code>, the "
                "template in <code>&lt;name&gt;_templates.xml</code>.</p>"),
            'files': {
                '__manifest__.py': manifest(*DATA),
                'report/contact_card_reports.xml': reports(ACTION),
                'report/contact_card_templates.xml': TEMPLATE_V1,
            },
            'live': [],
            'live_note': _lt(
                "A record of <code>ir.actions.report</code>, bound to the contacts, and a view of type "
                "<code>qweb</code>: the template."),
            'code_note': _lt("Click <b>Upgrade</b>: only XML."),
            'see': 'form',
            'see_text': _lt("Open a contact, then Print > Contact Card."),
        },
        {
            'key': 'template',
            'title': _lt("A template worth printing"),
            'explain': _lt(
                "<p>QWeb, the templates of Odoo, is HTML with <code>t-</code> attributes:</p>"
                "<ul><li><code>t-out</code> with the <code>contact</code> widget of "
                "<code>t-options</code> formats the contact itself: its address, phone and email;</li>"
                "<li><code>t-if</code> shows a part only when there is something to show;</li>"
                "<li><code>t-foreach</code> repeats a line for each contact of the company, and "
                "<code>t-out</code> writes a value.</li></ul>"
                "<p>The classes are Bootstrap's: <code>table table-sm</code>.</p>"),
            'files': {'report/contact_card_templates.xml': TEMPLATE_V2},
            'live': [],
            'live_note': _lt("The <code>arch</code> of the template changed: print again."),
            'code_note': _lt("Click <b>Upgrade</b>, then print again."),
            'see': 'form',
            'see_text': _lt("Print a company with contacts: the table lists them."),
        },
        {
            'key': 'paper',
            'title': _lt("A paper format"),
            'explain': _lt(
                "<p>A card is not a letter: a <b>paper format</b> (<code>report.paperformat</code>) "
                "sets the size, A5, the orientation, and the margins. <code>margin_top</code> "
                "leaves room for the header of the company.</p>"
                "<p>The report names it in <code>paperformat_id</code>; it comes first in the "
                "file, as a record must exist before another names it.</p>"),
            'files': {'report/contact_card_reports.xml': reports(PAPER, ACTION_PAPER)},
            'live': [],
            'live_note': _lt("A record of <code>report.paperformat</code>, set on the report."),
            'code_note': _lt("Click <b>Upgrade</b>, then print again."),
            'see': 'form',
            'see_text': _lt("Print it again: an A5 card, in landscape."),
        },
        {
            'key': 'finish',
            'title': _lt("Print it!"),
            'finish': True,
            'explain': _lt(
                "<p>A report in the Print menu, a QWeb template in the company's layout, a paper "
                "format: everything Odoo's invoices are made of.</p>"
                "<p><b>Export as app</b> gives you the module as a zip.</p>"),
            'files': {},
            'see': 'form',
            'see_text': _lt("Open a contact and print its card."),
        },
    ],
}
