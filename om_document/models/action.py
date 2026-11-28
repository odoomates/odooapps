import ast

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain


class DocumentsAction(models.Model):
    """ A workflow action offered on the documents of a folder: move and tag them, schedule an activity, and make
    a record from each of them, e.g. a vendor bill. The bridges add the kinds of records it makes. """
    _name = 'om.documents.action'
    _description = 'Document Action'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    folder_id = fields.Many2one('om.documents.folder', string='Folder', index=True, ondelete='cascade',
                                help='Offered on the documents of this folder and its subfolders. Leave empty to '
                                     'offer it on all the documents.')
    required_tag_ids = fields.Many2many('om.documents.tag', 'om_documents_action_required_tag_rel', 'action_id',
                                        'tag_id', string='Only With Tags',
                                        help='Offered on the documents having all these tags.')
    domain = fields.Char(string='Only For', default='[]',
                         help='Offered on the documents matching this filter.')

    # what it does
    move_folder_id = fields.Many2one('om.documents.folder', string='Move To', ondelete='set null')
    add_tag_ids = fields.Many2many('om.documents.tag', 'om_documents_action_add_tag_rel', 'action_id', 'tag_id',
                                   string='Add Tags')
    remove_tag_ids = fields.Many2many('om.documents.tag', 'om_documents_action_remove_tag_rel', 'action_id',
                                      'tag_id', string='Remove Tags')
    owner_id = fields.Many2one('res.users', string='Set Owner', domain=[('share', '=', False)])
    partner_id = fields.Many2one('res.partner', string='Set Contact')
    activity_type_id = fields.Many2one('mail.activity.type', string='Schedule Activity')
    activity_summary = fields.Char(string='Activity Summary')
    activity_user_id = fields.Many2one('res.users', string='Activity For', domain=[('share', '=', False)],
                                       help='Leave empty for the owner of the document.')
    activity_days = fields.Integer(string='Due In (days)')
    archive = fields.Boolean(string='Archive the Documents')
    create_model = fields.Selection([
        ('none', 'Nothing'),
        ('record', 'A Record'),
    ], string='Create', required=True, default='none')
    model_id = fields.Many2one('ir.model', string='Record Of', ondelete='cascade',
                               domain=[('transient', '=', False)])
    model_name = fields.Char(related='model_id.model')
    binary_field_id = fields.Many2one(
        'ir.model.fields', string='File In Field', ondelete='set null',
        domain="[('model_id', '=', model_id), ('ttype', '=', 'binary'), ('store', '=', True)]",
        help='Also put the file in this field of the record. It is attached to the record in any case.')

    @api.constrains('create_model', 'model_id')
    def _check_model(self):
        for action in self:
            if action.create_model == 'record' and not action.model_id:
                raise ValidationError(self.env._('Choose the model of the records %s creates.', action.name))

    @api.constrains('domain')
    def _check_domain(self):
        for action in self:
            try:
                Domain(ast.literal_eval(action.domain or '[]')).validate(self.env['om.documents.document'])
            except (ValueError, SyntaxError) as error:
                raise ValidationError(self.env._('The filter of %(action)s is not valid: %(error)s',
                                                 action=action.name, error=error)) from None

    def _filter_documents(self, documents):
        """ :return: the documents among `documents` the action applies to """
        self.ensure_one()
        if self.folder_id:
            folders = self.folder_id._get_descendants()
            documents = documents.filtered(lambda d: d.folder_id in folders)
        if self.required_tag_ids:
            documents = documents.filtered(lambda d: self.required_tag_ids <= d.tag_ids)
        domain = ast.literal_eval(self.domain or '[]')
        if domain and documents:
            documents = documents.filtered_domain(domain)
        return documents

    @api.model
    def _get_available(self, documents):
        """ :return: the actions applying to all of `documents` """
        return self.search([]).filtered(lambda action: action._filter_documents(documents) == documents)

    def run(self, documents):
        """ Run the action on `documents`: :return: an action opening the records it made, or True """
        self.ensure_one()
        documents = self._filter_documents(documents)
        if not documents:
            raise UserError(self.env._('%s does not apply to these documents.', self.name))
        documents.check_access('write')
        records = self._create_records(documents)
        values = {}
        if self.move_folder_id:
            values['folder_id'] = self.move_folder_id.id
        if self.owner_id:
            values['owner_id'] = self.owner_id.id
        if self.partner_id:
            values['partner_id'] = self.partner_id.id
        tag_commands = [Command.link(tag.id) for tag in self.add_tag_ids] + \
                       [Command.unlink(tag.id) for tag in self.remove_tag_ids]
        if tag_commands:
            values['tag_ids'] = tag_commands
        if values:
            documents.write(values)
        if self.activity_type_id:
            for document in documents:
                document.activity_schedule(
                    activity_type_id=self.activity_type_id.id,
                    summary=self.activity_summary or self.name,
                    user_id=(self.activity_user_id or document.owner_id or self.env.user).id,
                    date_deadline=fields.Date.add(fields.Date.context_today(self), days=self.activity_days))
        for document in documents:
            document.message_post(body=self.env._('Action run: %s', self.name), subtype_xmlid='mail.mt_note')
        if self.archive:
            documents.action_archive()
        if records:
            return self._action_open_records(records)
        return True

    def _create_records(self, documents):
        """ :return: the records made from `documents`, by the method of the kind chosen in `create_model` """
        if self.create_model == 'none':
            return None
        method = getattr(self, '_create_records_%s' % self.create_model)
        return method(documents)

    def _create_records_record(self, documents):
        records = self.env[self.model_name]
        for document in documents:
            records |= document._create_record(self.model_name, self.binary_field_id.name or None)
        return records

    def _action_open_records(self, records):
        action = {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': records._name,
        }
        if len(records) == 1:
            action.update(res_id=records.id, view_mode='form', views=[(False, 'form')])
        else:
            action.update(domain=[('id', 'in', records.ids)], view_mode='list,form',
                          views=[(False, 'list'), (False, 'form')])
        return action
