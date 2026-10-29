# The courses of the Academy, in the order they are offered. A course is code,
# not data: its steps hold the files of the learner's module, which the
# Academy shows, writes, checks and builds live. The first one comes in
# subjects to pick from (first_app.THEMES), one course each.
from . import contacts, first_app, kanban, report, security

COURSES = first_app.COURSES + [contacts.COURSE, kanban.COURSE, report.COURSE, security.COURSE]
COURSES_BY_KEY = {course['key']: course for course in COURSES}
