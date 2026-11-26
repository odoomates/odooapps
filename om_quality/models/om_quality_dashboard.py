from odoo import api, fields, models
from odoo.fields import Domain


class OmQualityDashboard(models.AbstractModel):
    _name = 'om.quality.dashboard'
    _description = 'Quality Dashboard'

    @api.model
    def get_data(self, days=30):
        days = int(days or 30)
        Check = self.env['om.quality.check']
        Alert = self.env['om.quality.alert']
        Action = self.env['om.quality.action']
        since = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        company = Domain('company_id', 'in', self.env.companies.ids)
        done = company & Domain('state', 'in', ('passed', 'failed')) & Domain('date_done', '>=', since)
        failed = company & Domain('state', '=', 'failed') & Domain('date_done', '>=', since)
        states = dict(Check._read_group(done, ['state'], ['__count']))
        passed_count = states.get('passed', 0)
        failed_count = states.get('failed', 0)
        done_count = passed_count + failed_count
        today = fields.Date.context_today(self)

        def top(groupby, domain, limit=6):
            rows = Check._read_group(domain, [groupby], ['__count'], order='__count desc', limit=limit)
            return [{'id': record.id, 'name': record.display_name, 'count': count} for record, count in rows if record]

        def rate_by(groupby, limit=6):
            rows = Check._read_group(done, [groupby, 'state'], ['__count'])
            data = {}
            for record, state, count in rows:
                if not record:
                    continue
                entry = data.setdefault(record.id, {'id': record.id, 'name': record.display_name, 'passed': 0, 'failed': 0})
                entry[state] += count
            result = sorted(data.values(), key=lambda e: (-e['failed'], -(e['passed'] + e['failed'])))[:limit]
            for entry in result:
                total = entry['passed'] + entry['failed']
                entry['rate'] = round(100.0 * entry['passed'] / total, 1) if total else 0.0
            return result

        stages = []
        for stage, count in Alert._read_group(company & Domain('active', '=', True), ['stage_id'], ['__count']):
            stages.append({'id': stage.id, 'name': stage.display_name or self.env._('No Stage'),
                           'count': count, 'closed': stage.is_closed, 'sequence': stage.sequence})
        stages.sort(key=lambda s: s['sequence'])

        return {
            'days': days,
            'kpi': {
                'todo': Check.search_count(company & Domain('state', '=', 'todo')),
                'waiting': Check.search_count(company & Domain('blocking_pending', '=', True)),
                'done': done_count,
                'failed': failed_count,
                'pass_rate': round(100.0 * passed_count / done_count, 1) if done_count else 0.0,
                'alerts_open': Alert.search_count(company & Domain('is_closed', '=', False)),
                'actions_late': Action.search_count(
                    company & Domain('state', '=', 'open') & Domain('date_deadline', '<', today)),
                'actions_open': Action.search_count(company & Domain('state', '=', 'open')),
            },
            'products': rate_by('product_id'),
            'partners': rate_by('partner_id'),
            'reasons': top('reason_id', failed),
            'points': rate_by('point_id'),
            'stages': stages,
            'since': fields.Datetime.to_string(since),
        }
