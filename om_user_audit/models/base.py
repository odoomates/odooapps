# The data events. Reads are logged per client call (Odoo's own code reads all
# the time and is never logged); creates, edits and deletes per record, whoever
# makes them but the superuser, since they change data.
from odoo import api, models

READ_METHODS = frozenset({
    'read', 'search_read', 'web_search_read', 'web_read_group', 'read_group',
})
SKIPPED_FIELDS = frozenset({'write_date', 'write_uid', 'create_date', 'create_uid', '__last_update'})
VALUE_LENGTH = 200


class Base(models.AbstractModel):
    _inherit = 'base'

    def _om_audit(self, operation):
        """ Whether ``operation`` on this model, by the current user, is logged. """
        if self.env.su or self.env.context.get('om_user_audit_off') or not self.env.registry.ready:
            return False
        return self.env['om.user.audit.rule']._om_should_log(self._name, operation, self.env.uid)

    def _om_audit_value(self, name):
        """ A field's value of one record, as a person reads it. """
        field = self._fields[name]
        value = self[name]
        if field.type == 'binary':
            return '(file)' if value else ''
        if field.type in ('many2one', 'many2one_reference') and hasattr(value, 'display_name'):
            return value.display_name or ''
        if field.relational:
            names = value.mapped('display_name')
            text = ', '.join(names[:10]) + (f' (+{len(names) - 10})' if len(names) > 10 else '')
            return text
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, value or '')
        if value is False and field.type != 'boolean':
            return ''
        text = str(value)
        return text if len(text) <= VALUE_LENGTH else text[:VALUE_LENGTH] + '...'

    def _om_audit_values(self, names):
        records = self.sudo().with_context(active_test=False, prefetch_fields=False)
        return {
            record.id: {name: record._om_audit_value(name) for name in names}
            for record in records
        }

    def _om_audit_names(self, vals):
        return [
            name for name in vals
            if name in self._fields and name not in SKIPPED_FIELDS and self._fields[name].store
            # computed fields count when a person can edit them (a price, a salesperson)
            and not (self._fields[name].compute and self._fields[name].readonly)
        ]

    def _om_audit_buffer(self, vals_list):
        self.env['om.user.audit.log']._om_buffer(vals_list)

    #
    # changes
    #

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if records and self._om_audit('create'):
            Log = self.env['om.user.audit.log']
            self._om_audit_buffer([
                Log._om_values('create', model=self._name, res_id=record.id,
                               res_name=record.sudo().display_name, method='create')
                for record in records
            ])
        return records

    def write(self, vals):
        if not self or not self._om_audit('write'):
            return super().write(vals)
        names = self._om_audit_names(vals)
        if not names:
            return super().write(vals)
        before = self._om_audit_values(names)
        result = super().write(vals)
        after = self._om_audit_values(names)
        Log = self.env['om.user.audit.log']
        labels = {name: self._fields[name]._description_string(self.env) for name in names}
        lines = []
        for record in self:
            changed = [
                f"{labels[name]}: {before[record.id][name]} → {after[record.id][name]}"
                for name in names if before[record.id][name] != after[record.id][name]
            ]
            if changed:
                lines.append(Log._om_values(
                    'write', model=self._name, res_id=record.id, res_name=record.sudo().display_name,
                    method='write', changes='\n'.join(changed)))
        self._om_audit_buffer(lines)
        return result

    def unlink(self):
        if not self or not self._om_audit('unlink'):
            return super().unlink()
        Log = self.env['om.user.audit.log']
        lines = [
            Log._om_values('unlink', model=self._name, res_id=record.id,
                           res_name=record.sudo().display_name, method='unlink')
            for record in self.sudo().exists()
        ]
        result = super().unlink()
        self._om_audit_buffer(lines)
        return result

    #
    # reads, exports and imports a client asks for
    #

    def _om_audit_read(self, method, ids, fields=None, count=None):
        if self.env.context.get('om_user_audit_exporting'):
            return
        if not (self._om_rpc_entry(method) and self._om_audit('read')):
            return
        ids = [record_id for record_id in ids if isinstance(record_id, int)]
        self._om_audit_buffer([self.env['om.user.audit.log']._om_values(
            'read', model=self._name, method=method, record_ids=ids,
            record_count=len(ids) if count is None else count,
            detail=', '.join(sorted(fields)) if fields else False,
        )])

    def read(self, fields=None, load='_classic_read'):
        result = super().read(fields, load)
        self._om_audit_read('read', self.ids, fields)
        return result

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **read_kwargs):
        result = super().search_read(domain, fields, offset, limit, order, **read_kwargs)
        self._om_audit_read('search_read', [row.get('id') for row in result], fields)
        return result

    @api.model
    def web_search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        result = super().web_search_read(domain, fields, offset=offset, limit=limit, order=order)
        self._om_audit_read('web_search_read', [row.get('id') for row in result.get('records', ())],
                            fields)
        return result

    @api.model
    def web_read_group(self, domain, fields, groupby, *args, **kwargs):
        result = super().web_read_group(domain, fields, groupby, *args, **kwargs)
        if isinstance(result, dict):
            self._om_audit_read('web_read_group', [], [groupby] if isinstance(groupby, str) else groupby, count=len(result.get('groups', ())))
        return result

    @api.model
    def read_group(self, domain, fields, groupby, *args, **kwargs):
        result = super().read_group(domain, fields, groupby, *args, **kwargs)
        self._om_audit_read('read_group', [], [groupby] if isinstance(groupby, str) else groupby, count=len(result))
        return result

    def export_data(self, fields_to_export):
        # Odoo 15 reads the records to export: the export is logged, not that read
        result = super(Base, self.with_context(om_user_audit_exporting=True)).export_data(fields_to_export)
        if (self._om_rpc_entry('export_data') or self._om_rpc_entry('*')) and self._om_audit('export'):
            self._om_audit_buffer([self.env['om.user.audit.log']._om_values(
                'export', model=self._name, method='export_data', record_ids=self.ids,
                detail=', '.join(fields_to_export))])
        return result

    @api.model
    def load(self, fields, data):
        result = super().load(fields, data)
        if self._om_audit('import'):
            ids = [record_id for record_id in result.get('ids') or () if record_id]
            self._om_audit_buffer([self.env['om.user.audit.log']._om_values(
                'import', model=self._name, method='load', record_ids=ids,
                detail=', '.join(fields))])
        return result


class BaseClearCache(models.AbstractModel):
    """ Odoo 20 clears the cache named by a model's _clear_cache_name when its
    records change; the models of these modules rely on it. Odoo 15 has a
    single cache: it is cleared whole. """
    _inherit = 'base'

    def _om_clear_cache(self):
        if getattr(self, '_clear_cache_name', ''):
            self.env.registry.clear_caches()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._om_clear_cache()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._om_clear_cache()
        return result

    def unlink(self):
        self._om_clear_cache()
        return super().unlink()
