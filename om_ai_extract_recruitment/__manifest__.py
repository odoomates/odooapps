{
    'name': 'AI CV Reading - Fill Applicants from CVs with Your Own AI',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'Read CVs with your own AI model: name, email, phone, LinkedIn, degree, availability, tags and a '
               'summary of experience, education, skills and languages filled on the applicant for review',
    'description': """
Reads the CV attached to an applicant with the AI engine and fills the empty fields: name, email, phone, LinkedIn
profile, degree, availability and existing tags, with a summary of the experience, the education, the skills and
the languages in the notes. Values already set are never replaced.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_ai_extract', 'hr_recruitment'],
    'data': [
        'data/hr_applicant_data.xml',
        'views/hr_applicant_views.xml',
    ],
    'installable': True,
    'auto_install': True,
    'application': False,
}
