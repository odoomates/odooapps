{
    'name': 'Odoo Mates Pen',
    'version': '20.0.1.0.1',
    'category': 'Productivity',
    'summary': 'Add Fields, Change Fields, View Customizer Odoo 20, Hide Fields, Rename Fields, Readonly Fields, No Code',
    'description': """
Customize your views without writing XML.

A button in the navbar turns on customize mode. Every field on the screen gets a pencil:
click it to rename the field, hide it, make it readonly or required, restrict it to
chosen user groups, change its widget, or stop a many2one from being opened or created
inline, or hide it behind a condition built from rows instead of typed as code. Mirror
a value from a linked record with a related field. Drag fields to reorder them. Add fields that are not on the view yet, or create
brand new ones, and drag them where they should go, including onto a notebook tab to
drop them inside that page. Add fields to the list and the form embedded in a one2many.
Add pages to a notebook. Turn off New, Edit, Delete, Duplicate, Export and Import per
view.

Changes are drafts until you publish them. Edit as much as you like: nobody else sees
anything until you press Publish, and what is already published keeps running in the
meantime. Discard throws the unpublished work away and leaves the live view alone.

Every change is stored as a rule and the inherited view is generated from those rules,
so a customization can always be switched off without touching XML, and a customization
that no longer matches its standard view is flagged before it breaks an upgrade.

Everything can be exported as a real installable module, so the same setup can be
replayed on another database.
""",
    'sequence': 10,
    'author': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'depends': ['web'],
    'data': [
        'security/security.xml',
        'views/om_pen_views.xml',
        'security/ir.access.csv',
    ],
    'uninstall_hook': 'uninstall_hook',
    'assets': {
        'web.assets_backend': [
            'om_pen/static/src/**/*',
        ],
        'web.assets_tests': [
            'om_pen/static/tests/tours/*.js',
        ],
    },
    'live_test_url': 'https://www.youtube.com/watch?v=i-6JEtXyjXY',
    'license': 'LGPL-3',
    'images': ['static/description/banner.gif'],
}
