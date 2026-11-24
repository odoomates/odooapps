from odoo import api, fields, models


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def _get_view_fields(self, view_type, models):
        if view_type == 'gantt':
            # group rows can use any groupable field of the model
            models[self._name] = list(self._fields.keys())
            return models
        return super()._get_view_fields(view_type, models)

    @api.model
    def get_gantt_data(self, domain, groupby, read_specification, order=None, limit=None,
                       gantt_range=None, unavailability=False, progress_bar_fields=None):
        """ Return the records and the groups shown by a gantt view.

        :param domain: search domain, including the visible date range
        :param groupby: list of groupby specifications (rows and sub-rows)
        :param read_specification: web_read specification of the records
        :param order: order of the records
        :param limit: maximum number of records
        :param gantt_range: dict with ``start``, ``stop`` (UTC datetimes as strings) and ``scale``
            of the visible range
        :param unavailability: compute the unavailable periods of each row with
            :meth:`gantt_unavailability`
        :param progress_bar_fields: grouped fields whose rows show a progress bar, computed by
            :meth:`_gantt_progress_bar`
        :return: dict with ``records``, ``groups``, ``length``, ``unavailabilities`` and
            ``progress_bars``
        """
        groupby = list(groupby or [])
        groups = []
        if groupby:
            groups = self.with_context(read_group_expand=True).formatted_read_group(
                domain, groupby, ['id:array_agg'],
            )
        records = self.search(domain, order=order, limit=limit)
        length = len(records)
        if limit and length >= limit:
            length = self.search_count(domain)
        result = {
            'records': records.web_read(read_specification),
            'groups': groups,
            'length': length,
            'unavailabilities': [],
            'progress_bars': {},
        }
        if not gantt_range:
            return result
        start = fields.Datetime.to_datetime(gantt_range['start'])
        stop = fields.Datetime.to_datetime(gantt_range['stop'])
        if unavailability:
            rows = self._gantt_rows_from_groups(groupby, groups)
            rows = self.gantt_unavailability(start, stop, gantt_range.get('scale'), groupby, rows)
            result['unavailabilities'] = self._gantt_flatten_unavailability(rows or [])
        for field_name in progress_bar_fields or []:
            if field_name not in groupby or field_name not in self._fields:
                continue
            res_ids = set()
            for group in groups:
                value = group.get(field_name)
                if isinstance(value, (list, tuple)):
                    value = value[0] if value else False
                if value:
                    res_ids.add(value)
            if res_ids:
                bars = self._gantt_progress_bar(field_name, sorted(res_ids), start, stop) or {}
                result['progress_bars'][field_name] = {str(key): value for key, value in bars.items()}
        return result

    @api.model
    def _gantt_progress_bar(self, field, res_ids, start, stop):
        """ Hook for the progress bar shown in the header of the rows grouped by ``field``
        (fields listed in the ``progress_bar`` attribute of the gantt view).

        :param str field: name of the grouped field
        :param list res_ids: values of the rows (ids for relational fields)
        :param datetime start: start of the visible range (UTC)
        :param datetime stop: end of the visible range (UTC)
        :return: dict ``{res_id: {'value': float, 'max': float}}``, optionally with
            ``'label'`` (text shown in the bar) for each row; rows without an entry show no bar
        """
        return {}

    @api.model
    def _gantt_rows_from_groups(self, groupby, groups):
        """ Build the nested rows given to :meth:`gantt_unavailability`. """
        root = {'groupedBy': [], 'resId': False, 'rows': [], 'path': []}

        def value_of(value):
            if isinstance(value, (list, tuple)):
                return value[0] if value else False
            return value

        for group in groups:
            parent = root
            for index, spec in enumerate(groupby):
                res_id = value_of(group.get(spec))
                row = next((r for r in parent['rows'] if r['resId'] == res_id), None)
                if row is None:
                    row = {
                        'groupedBy': groupby[:index + 1],
                        'resId': res_id,
                        'rows': [],
                        'path': parent['path'] + [res_id],
                    }
                    parent['rows'].append(row)
                parent = row
        return [root] if not groupby else root['rows']

    @api.model
    def _gantt_flatten_unavailability(self, rows):
        result = []
        for row in rows:
            periods = [
                {
                    'start': fields.Datetime.to_string(period['start']),
                    'stop': fields.Datetime.to_string(period['stop']),
                }
                for period in row.get('unavailabilities') or []
            ]
            if periods:
                result.append({'path': row.get('path', []), 'unavailabilities': periods})
            result += self._gantt_flatten_unavailability(row.get('rows') or [])
        return result

    @api.model
    def gantt_unavailability(self, start_date, end_date, scale, group_bys=None, rows=None):
        """ Hook to grey out the periods of a gantt row where planning is not possible
        (non-working days, closed days, resource not available...).

        Override it in a model and set ``display_unavailability="1"`` on its gantt view.
        Each row is a dict with ``groupedBy`` (the groupby specifications of the row),
        ``resId`` (the value of the row for its last groupby, an id for relational fields)
        and ``rows`` (its sub-rows). When the view is not grouped, a single row with an
        empty ``groupedBy`` is given. Add to each row a key ``unavailabilities``: a list of
        dicts with ``start`` and ``stop`` naive UTC datetimes.

        :param datetime start_date: start of the visible range (UTC)
        :param datetime end_date: end of the visible range (UTC)
        :param str scale: day, week, month or year
        :param list group_bys: groupby specifications of the view
        :param list rows: nested rows of the view
        :return: the rows, with their unavailabilities
        """
        return rows
