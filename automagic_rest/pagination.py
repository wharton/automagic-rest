import re

from django.db import connections

from rest_framework.pagination import LimitOffsetPagination


def parse_explain(explain_string):
    """
    Parses an individual row of a PostgreSQL explain query.
    This can parse either the full result, or the minimized version
    that Django returns, search for `rows=`.
    """

    return int(re.search("rows=([0-9]+) ", explain_string).group(1))


def estimate_count(db_name, query):
    """
    This will give us a close estimate count of the number of rows in the table
    by using the execution plan. This returns the estimated number of rows by
    analyzing the result from PostgreSQL.

    See: https://wiki.postgresql.org/wiki/Count_estimate
    """

    cursor = connections[db_name].cursor()
    cursor.execute(f"EXPLAIN {query}")
    rows = cursor.fetchall()

    for row in rows:
        # Loop through the results of the EXPLAIN, grab the first appearance of `rows=`
        if "rows=" in row[0]:
            estimate_rows = parse_explain(row[0])
            break

    return estimate_rows


class CountEstimatePagination(LimitOffsetPagination):
    """
    This subclasses LimitOffsetPagination to use the estimated count from the
    PostgreSQL query plan, eliminating the long wait time for `SELECT COUNT(*)`.
    """

    def paginate_queryset(self, queryset, request, view=None):
        self.count = parse_explain(queryset.explain())
        self.limit = self.get_limit(request)
        if self.limit is None:
            return None

        self.offset = self.get_offset(request)
        self.request = request
        if self.count > self.limit and self.template is not None:
            self.display_page_controls = True

        if self.count == 0 or self.offset > self.count:
            return []
        return list(queryset[self.offset : self.offset + self.limit])
