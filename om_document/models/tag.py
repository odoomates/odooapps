from random import randint

from odoo import fields, models


class DocumentsTagCategory(models.Model):
    """ A group of tags, e.g. Status or Year, offered on the documents of a folder and of its subfolders, or on all
    the documents when it has no folder. """
    _name = 'om.documents.tag.category'
    _description = 'Document Tag Category'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    folder_id = fields.Many2one('om.documents.folder', string='Folder', index=True, ondelete='cascade',
                                help='Offered in this folder and its subfolders. Leave empty to offer it everywhere.')
    tag_ids = fields.One2many('om.documents.tag', 'category_id', string='Tags')
    tooltip = fields.Char(help='Explains the category to the users tagging documents.')

    _name_uniq = models.Constraint('UNIQUE(name, folder_id)', 'A category name is used once per folder.')


class DocumentsTag(models.Model):
    _name = 'om.documents.tag'
    _description = 'Document Tag'
    _order = 'category_sequence, sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    category_id = fields.Many2one('om.documents.tag.category', string='Category', index=True, ondelete='cascade')
    category_sequence = fields.Integer(related='category_id.sequence', store=True, string='Category Sequence')
    folder_id = fields.Many2one(related='category_id.folder_id', store=True, index=True)
    color = fields.Integer(default=lambda self: randint(1, 11))

    _name_uniq = models.Constraint('UNIQUE(name, category_id)', 'A tag name is used once per category.')

    def _compute_display_name(self):
        for tag in self:
            tag.display_name = '%s: %s' % (tag.category_id.name, tag.name) if tag.category_id and \
                self.env.context.get('om_documents_tag_full_name') else tag.name

    def _domain_for_folder(self, folder):
        """ :return: the domain of the tags offered on the documents of `folder` """
        ancestors = [int(folder_id) for folder_id in (folder.parent_path or '').split('/') if folder_id]
        return ['|', ('folder_id', '=', False), ('folder_id', 'in', ancestors)]
