# Your turn: the challenges at the end of a course, no code shown. The learner
# does them in their module (Code it), or in Odoo's technical menus (Build it
# live), and the Academy checks what Odoo has: a field by its label and type,
# a field in a view, a filter, a required field, an operation of an access
# right. The same checks work on the module's model and on the live one.
from lxml import etree

from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)


class ChallengeChecker:

    def __init__(self, progress, course):
        self.progress = progress
        self.env = progress.env
        self.course = course
        self.live = progress.mode == 'live'

    def model(self, model):
        """ The model in this database: x_... built live, as named in the module otherwise. """
        name = self.progress._live().model_name(model) if self.live else model
        return self.env[name] if name in self.env else None

    def check(self, challenge):
        """ (ok, message) """
        return getattr(self, '_check_' + challenge['kind'])(challenge)

    def _field(self, Model, label):
        label = label.strip().lower()
        for name, field in Model._fields.items():
            if (field.string or '').strip().lower() == label:
                return name, field
        return None, None

    def _check_field(self, challenge):
        Model = self.model(challenge['model'])
        if Model is None:
            return False, str(_lt("Build the app first: its model is not in this database."))
        name, field = self._field(Model, challenge['label'])
        if not field:
            return False, str(_lt("No field labelled %(label)s yet.")) % {'label': challenge['label']}
        if field.type != challenge['type']:
            return False, str(_lt("%(label)s is a %(found)s: make it a %(type)s.")) % {
                'label': challenge['label'], 'found': field.type, 'type': challenge['type']}
        view = challenge.get('view')
        if view:
            arch = etree.fromstring(Model.get_view(view_type=view)['arch'])
            if not arch.xpath('//field[@name=$name]', name=name):
                return False, str(_lt("%(label)s is there, but not in the %(view)s view yet.")) % {
                    'label': challenge['label'], 'view': view}
        return True, str(_lt("Yes: %(label)s (%(name)s), a %(type)s field.")) % {
            'label': challenge['label'], 'name': name, 'type': field.type}

    def _check_filter(self, challenge):
        Model = self.model(challenge['model'])
        if Model is None:
            return False, str(_lt("Build the app first: its model is not in this database."))
        arch = etree.fromstring(Model.get_view(view_type='search')['arch'])
        label = challenge['label'].strip().lower()
        if any((node.get('string') or '').strip().lower() == label for node in arch.iter('filter')):
            return True, str(_lt("Yes: the search bar offers %(label)s.")) % {'label': challenge['label']}
        return False, str(_lt("No filter %(label)s in the search view yet.")) % {'label': challenge['label']}

    def _check_required(self, challenge):
        Model = self.model(challenge['model'])
        if Model is None:
            return False, str(_lt("Build the app first: its model is not in this database."))
        name = ('x_' + challenge['field']) if self.live else challenge['field']
        field = Model._fields.get(name)
        if field is not None and field.required:
            return True, str(_lt("Yes: %(name)s is required.")) % {'name': name}
        return False, str(_lt("%(name)s is not required yet.")) % {'name': name}

    def _check_access(self, challenge):
        Model = self.model(challenge['model'])
        if Model is None:
            return False, str(_lt("Build the app first: its model is not in this database."))
        if self.live:
            group = self.progress._live().record(challenge['group'])
        else:
            group = self.env.ref('%s.%s' % (self.course['module'], challenge['group']), raise_if_not_found=False)
        accesses = self.env['ir.access'].sudo().search([('model_id.model', '=', Model._name),
                                                        ('group_id', '=', group.id if group else False)])
        if any(challenge['operation'] in (access.operation or '') for access in accesses):
            return True, str(_lt("Yes: the group may %(what)s.")) % {'what': challenge['what']}
        return False, str(_lt("The group may not %(what)s yet.")) % {'what': challenge['what']}

    def _check_report(self, challenge):
        report = self.env['ir.actions.report'].sudo().search([('model', '=', challenge['model']),
                                                              ('name', '=ilike', challenge['label'])], limit=1)
        if not report:
            return False, str(_lt("No report named %(label)s on %(model)s yet.")) % {
                'label': challenge['label'], 'model': challenge['model']}
        if not report.binding_model_id:
            return False, str(_lt("%(label)s is there, but not in the Print menu yet.")) % {'label': challenge['label']}
        return True, str(_lt("Yes: %(label)s is in the Print menu.")) % {'label': challenge['label']}
