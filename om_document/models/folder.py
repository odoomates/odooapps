import ast

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain

ACCESS_LEVELS = [
    ('none', 'No Access'),
    ('view', 'View'),
    ('edit', 'Edit'),
]


class DocumentsFolder(models.Model):
    """ A folder of documents, in a tree. Who reaches it is set on the folder: all the internal users, groups or
    users, reading or editing, and its owner. A subfolder inherits the access of its parent, and adds its own.

    The access the folder gives, inherited included, is kept in the ``eff_*`` fields that the access rules read.
    A private folder (My Drive) is reached by its owner only.
    """
    _name = 'om.documents.folder'
    _inherit = ['mail.thread', 'mail.alias.mixin.optional']
    _description = 'Document Folder'
    _parent_store = True
    _parent_name = 'parent_id'
    _order = 'sequence, name, id'
    _rec_names_search = ['name', 'complete_name']
    _check_company_auto = True

    name = fields.Char(required=True, translate=True, tracking=True)
    complete_name = fields.Char(string='Full Name', compute='_compute_complete_name', recursive=True, store=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    parent_id = fields.Many2one('om.documents.folder', string='Parent Folder', index=True, ondelete='cascade',
                                tracking=True, check_company=True)
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('om.documents.folder', 'parent_id', string='Subfolders')
    company_id = fields.Many2one('res.company', index=True, tracking=True,
                                 help='Leave empty to share the folder with all the companies.')
    owner_id = fields.Many2one('res.users', string='Owner', default=lambda self: self.env.user, index=True,
                               tracking=True, domain=[('share', '=', False)],
                               help='Always reaches and edits the folder.')
    description = fields.Html()
    color = fields.Integer()
    is_private = fields.Boolean(
        string='Private', readonly=True,
        help='The My Drive of its owner: nobody else reaches it, nor its subfolders unless they are shared.')
    private_user_id = fields.Many2one(
        'res.users', string='Private To', compute='_compute_private_user_id', store=True, recursive=True,
        index='btree_not_null')

    # access set on the folder
    inherit_access = fields.Boolean(
        string='Inherit Access', default=True,
        help='Reached by whoever reaches the parent folder, and by the groups and users below.')
    access_internal = fields.Selection(
        ACCESS_LEVELS, string='Internal Users', default='view', required=True,
        help='What every Documents user can do in the folder.')
    read_group_ids = fields.Many2many('res.groups', 'om_documents_folder_read_group_rel', 'folder_id', 'group_id',
                                      string='Read Groups')
    write_group_ids = fields.Many2many('res.groups', 'om_documents_folder_write_group_rel', 'folder_id',
                                       'group_id', string='Write Groups')
    read_user_ids = fields.Many2many('res.users', 'om_documents_folder_read_user_rel', 'folder_id', 'user_id',
                                     string='Read Users', domain=[('share', '=', False)])
    write_user_ids = fields.Many2many('res.users', 'om_documents_folder_write_user_rel', 'folder_id', 'user_id',
                                      string='Write Users', domain=[('share', '=', False)])

    # access in effect, inherited included: read by the access rules
    eff_access_internal = fields.Selection(
        ACCESS_LEVELS, string='Internal Users in Effect', compute='_compute_eff_access', store=True,
        recursive=True)
    eff_read_group_ids = fields.Many2many(
        'res.groups', 'om_documents_folder_eff_read_group_rel', 'folder_id', 'group_id',
        string='Read Groups in Effect', compute='_compute_eff_access', store=True, recursive=True)
    eff_write_group_ids = fields.Many2many(
        'res.groups', 'om_documents_folder_eff_write_group_rel', 'folder_id', 'group_id',
        string='Write Groups in Effect', compute='_compute_eff_access', store=True, recursive=True)
    eff_read_user_ids = fields.Many2many(
        'res.users', 'om_documents_folder_eff_read_user_rel', 'folder_id', 'user_id',
        string='Read Users in Effect', compute='_compute_eff_access', store=True, recursive=True)
    eff_write_user_ids = fields.Many2many(
        'res.users', 'om_documents_folder_eff_write_user_rel', 'folder_id', 'user_id',
        string='Write Users in Effect', compute='_compute_eff_access', store=True, recursive=True)

    tag_category_ids = fields.One2many('om.documents.tag.category', 'folder_id', string='Tag Categories')
    alias_tag_ids = fields.Many2many('om.documents.tag', 'om_documents_folder_alias_tag_rel', 'folder_id', 'tag_id',
                                     string='Tags of Emailed Documents',
                                     help='Set on the documents created from the files emailed to the folder.')
    action_ids = fields.One2many('om.documents.action', 'folder_id', string='Actions')
    document_ids = fields.One2many('om.documents.document', 'folder_id', string='Documents')
    document_count = fields.Integer(compute='_compute_document_count')
    can_edit = fields.Boolean(compute='_compute_can_edit')

    _check_parent = models.Constraint('CHECK(id != parent_id)', 'A folder cannot be its own parent.')

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for folder in self:
            folder.complete_name = '%s / %s' % (folder.parent_id.complete_name, folder.name) \
                if folder.parent_id else folder.name

    @api.depends('is_private', 'owner_id', 'parent_id.private_user_id')
    def _compute_private_user_id(self):
        for folder in self:
            folder.private_user_id = folder.owner_id if folder.is_private else folder.parent_id.private_user_id

    @api.depends('inherit_access', 'access_internal', 'read_group_ids', 'write_group_ids', 'read_user_ids',
                 'write_user_ids', 'parent_id', 'parent_id.owner_id', 'parent_id.eff_access_internal',
                 'parent_id.eff_read_group_ids', 'parent_id.eff_write_group_ids', 'parent_id.eff_read_user_ids',
                 'parent_id.eff_write_user_ids')
    def _compute_eff_access(self):
        for folder in self:
            parent = folder.parent_id
            if folder.inherit_access and parent:
                folder.eff_access_internal = parent.eff_access_internal
                folder.eff_read_group_ids = parent.eff_read_group_ids | folder.read_group_ids
                folder.eff_write_group_ids = parent.eff_write_group_ids | folder.write_group_ids
                folder.eff_read_user_ids = parent.eff_read_user_ids | folder.read_user_ids
                # the owner of the parent folder keeps editing what is inside it
                folder.eff_write_user_ids = parent.eff_write_user_ids | parent.owner_id | folder.write_user_ids
            else:
                folder.eff_access_internal = 'none' if folder.is_private else folder.access_internal
                folder.eff_read_group_ids = folder.read_group_ids
                folder.eff_write_group_ids = folder.write_group_ids
                folder.eff_read_user_ids = folder.read_user_ids
                folder.eff_write_user_ids = folder.write_user_ids

    def _compute_document_count(self):
        counts = dict(self.env['om.documents.document']._read_group(
            [('folder_id', 'in', self.ids)], ['folder_id'], ['__count']))
        for folder in self:
            folder.document_count = counts.get(folder, 0)

    def _compute_can_edit(self):
        editable = self._filtered_access('write')
        for folder in self:
            folder.can_edit = folder in editable

    @api.constrains('parent_id')
    def _check_parent_recursion(self):
        if self._has_cycle():
            raise ValidationError(self.env._('A folder cannot be inside one of its own subfolders.'))

    @api.constrains('is_private', 'parent_id')
    def _check_private(self):
        for folder in self:
            if folder.is_private and folder.parent_id:
                raise ValidationError(self.env._('A private folder is at the top of the tree.'))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not self.env.user.has_group('om_document.group_documents_manager'):
            for vals in vals_list:
                parent = self.browse(vals.get('parent_id'))
                if not parent:
                    raise AccessError(self.env._('Only a Documents administrator creates a folder at the top of '
                                                 'the tree: create it inside a folder you edit.'))
                parent.check_access('write')
        folders = super().create(vals_list)
        folders.filtered('alias_id')._sync_alias_defaults()
        return folders

    def write(self, vals):
        if 'parent_id' in vals and vals['parent_id'] and not self.env.su:
            self.browse(vals['parent_id']).check_access('write')
        result = super().write(vals)
        if {'alias_tag_ids', 'alias_name', 'owner_id'} & set(vals):
            self.filtered('alias_id')._sync_alias_defaults()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_private(self):
        if any(folder.is_private for folder in self) and not self.env.su:
            raise UserError(self.env._('A My Drive folder is not deleted.'))

    # ------------------------------------------------------------------
    # My Drive
    # ------------------------------------------------------------------

    @api.model
    def _get_my_drive(self, user=None):
        """ :return: the private folder of `user`, the current one by default, created the first time """
        user = user or self.env.user
        folder = self.sudo().with_context(active_test=False).search(
            [('is_private', '=', True), ('owner_id', '=', user.id)], limit=1)
        if not folder:
            folder = self.sudo().create({
                'name': self.env._('My Drive'),
                'is_private': True,
                'owner_id': user.id,
                'inherit_access': False,
                'access_internal': 'none',
                'sequence': 0,
            })
        return folder.sudo(False)

    # ------------------------------------------------------------------
    # Upload by email
    # ------------------------------------------------------------------

    def _alias_get_creation_values(self):
        values = super()._alias_get_creation_values()
        values['alias_model_id'] = self.env['ir.model']._get_id('om.documents.document')
        if self.id:
            values['alias_defaults'] = repr(self._alias_document_defaults())
        return values

    def _alias_document_defaults(self):
        self.ensure_one()
        defaults = {'folder_id': self.id, 'owner_id': self.owner_id.id}
        if self.alias_tag_ids:
            defaults['tag_ids'] = [(6, 0, self.alias_tag_ids.ids)]
        return defaults

    def _sync_alias_defaults(self):
        for folder in self:
            defaults = ast.literal_eval(folder.alias_id.alias_defaults or '{}')
            defaults.update(folder._alias_document_defaults())
            folder.alias_id.sudo().write({
                'alias_defaults': repr(defaults),
                'alias_model_id': self.env['ir.model']._get_id('om.documents.document'),
                'alias_parent_model_id': self.env['ir.model']._get_id(self._name),
                'alias_parent_thread_id': folder.id,
            })

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _get_descendants(self):
        """ :return: the folders and all their subfolders """
        if not self:
            return self
        return self.search(Domain.OR(Domain('parent_path', '=like', '%s%%' % folder.parent_path)
                                     for folder in self))

    def action_open_documents(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_document.action_documents')
        action['context'] = {'searchpanel_default_folder_id': self.id, 'default_folder_id': self.id}
        return action

    def action_share(self):
        self.ensure_one()
        share = self.env['om.documents.share'].create({'share_type': 'folder', 'folder_id': self.id})
        return share._action_open()
