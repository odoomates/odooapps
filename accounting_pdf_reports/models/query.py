from odoo.tools.query import Query


def get_sql(self):
    """ Returns (query_from, query_where, query_params). """
    from_string, from_params = self.from_clause
    where_string, where_params = self.where_clause
    return from_string, where_string, from_params + where_params


Query.get_sql = get_sql
