from odoo import api, fields, models


class OmTallyMapping(models.Model):
    """ The Odoo record made from (or linked to) a record of Tally. Keyed by the GUID of Tally per company, so
    importing again never makes a duplicate, and a record renamed in Tally is still found. """
    _name = 'om.tally.mapping'
    _description = 'Tally Mapping'
    _order = 'tally_type, tally_name'

    company_id = fields.Many2one('res.company', required=True, index=True, ondelete='cascade')
    import_id = fields.Many2one('om.tally.import', string='Tally Import', ondelete='set null', index=True)
    tally_type = fields.Selection([
        ('group', 'Group'),
        ('ledger', 'Ledger'),
        ('party', 'Party'),
        ('journal', 'Journal'),
        ('tax', 'Tax'),
        ('cost_category', 'Cost Category'),
        ('cost_centre', 'Cost Centre'),
        ('unit', 'Unit'),
        ('stock_group', 'Stock Group'),
        ('stock_category', 'Stock Category'),
        ('stock_item', 'Stock Item'),
        ('godown', 'Godown'),
        ('batch', 'Batch'),
        ('voucher', 'Voucher'),
        ('opening', 'Opening Entry'),
        ('opening_stock', 'Opening Stock'),
        ('bill', 'Bill'),
    ], required=True, index=True)
    tally_guid = fields.Char(string='Tally GUID', required=True, index=True)
    tally_name = fields.Char(string='Tally Name')
    alter_id = fields.Integer(string='Alter ID')
    res_model = fields.Char(string='Odoo Model', required=True)
    res_id = fields.Many2oneReference(string='Odoo Record ID', model_field='res_model', required=True)
    record_ref = fields.Reference(selection='_selection_record_ref', string='Odoo Record',
                                  compute='_compute_record_ref')

    _unique_guid = models.Constraint(
        'UNIQUE(company_id, tally_type, tally_guid, res_model)',
        "A record of Tally is mapped once per company.",
    )

    @api.model
    def _selection_record_ref(self):
        return [(model.model, model.name) for model in self.env['ir.model'].sudo().search([])]

    @api.depends('res_model', 'res_id')
    def _compute_record_ref(self):
        for mapping in self:
            record = mapping.res_model in self.env and self.env[mapping.res_model].browse(mapping.res_id).exists()
            mapping.record_ref = f'{mapping.res_model},{mapping.res_id}' if record else False

    @api.model
    def _om_tally_find(self, company, tally_type, guid, res_model):
        """ The Odoo record mapped to a GUID of Tally, or an empty recordset. """
        if not guid:
            return self.env[res_model]
        mapping = self.search([('company_id', '=', company.id), ('tally_type', '=', tally_type),
                               ('tally_guid', '=', guid), ('res_model', '=', res_model)], limit=1)
        return self.env[res_model].browse(mapping.res_id).exists() if mapping else self.env[res_model]

    @api.model
    def _om_tally_set(self, import_record, tally_type, guid, record, name=None, alter_id=0):
        """ Map a GUID of Tally to an Odoo record (one record per GUID, model and company). """
        if not guid or not record:
            return self
        record.ensure_one()
        company = import_record.company_id
        mapping = self.search([('company_id', '=', company.id), ('tally_type', '=', tally_type),
                               ('tally_guid', '=', guid), ('res_model', '=', record._name)], limit=1)
        values = {'res_id': record.id, 'tally_name': name, 'alter_id': alter_id, 'import_id': import_record.id}
        if mapping:
            mapping.write(values)
            return mapping
        return self.create(dict(values, company_id=company.id, tally_type=tally_type, tally_guid=guid,
                                res_model=record._name))
