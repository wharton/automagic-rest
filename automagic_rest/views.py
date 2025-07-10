from importlib import import_module

from django.db import connections
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework_filters.backends import (
    ComplexFilterBackend,
    RestFrameworkFilterBackend,
)

from .pagination import estimate_count, CountEstimatePagination
from .settings import get_reserved_words_to_append_suffix, get_reserved_word_suffix


RESERVED_WORDS = get_reserved_words_to_append_suffix()
RESERVED_WORD_SUFFIX = get_reserved_word_suffix()


def split_basename(basename):
    """
    Splits a base name into schema and table names.
    """
    parts = basename.split(".")
    db_name = parts[0]
    python_path_name = parts[1]
    schema_name = parts[2]
    table_name = parts[3]

    return db_name, python_path_name, schema_name, table_name


def reserved_word_check(column_name):
    """
    Python RESERVED_WORDS are appended with `_var`, and columns ending with `_`
    are appended with `var` to avoid conflicts with URL double underscores.
    """
    changed = False
    if (
        column_name in RESERVED_WORDS
        or (column_name.endswith("_") and column_name != "__BLANK__")
    ):
        column_name = f"{column_name}{RESERVED_WORD_SUFFIX}"
        changed = True
    
    return column_name, changed


class GenericViewSet(ReadOnlyModelViewSet):
    """"""  # Supress this docstring from the DRF HTML browsable interface

    """
    A generic viewset which imports the necessary model, serializer, and permission
    for the endpoint.
    """
    index_sql = """
        SELECT DISTINCT a.attname AS index_column
        FROM pg_namespace n
        JOIN pg_class c ON n.oid = c.relnamespace
        JOIN pg_index i ON c.oid = i.indrelid
        JOIN pg_attribute a ON a.attnum = i.indkey[0]
            AND a.attrelid = c.oid
        WHERE n.nspname = %(schema_name)s
            AND c.relname = %(table_name)s
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        (
            self.db_name,
            self.python_path_name,
            self.schema_name,
            self.table_name,
        ) = split_basename(self.basename)

        self.model = getattr(
            import_module(f"{self.python_path_name}.models.{self.schema_name}"),
            f"{self.schema_name}_{self.table_name}_model",
        )

        if pagination_class := self.get_pagination_class():
            # Only override pagination if provided.
            self.pagination_class = pagination_class

        api_permission = self.get_permission()
        # Only override permissions if provided.
        if api_permission:
            self.permission_classes = (api_permission,)

        self.filter_backends = [OrderingFilter, SearchFilter]
        self.ordering_fields = "__all__"
        self.search_fields = []

        # Create a dictionary of key column names and values as their position
        self.positions = self.get_positions()

        # Add any columns indexed in the PostgreSQL database to be
        # filterable columns in the API
        index_columns = self.get_indexes()

        # If any columns are indexed, add the appropriate filter backends
        # and set up a dictionary of filter fields
        if len(index_columns):
            if RestFrameworkFilterBackend not in self.filter_backends:
                self.filter_backends += [RestFrameworkFilterBackend]
            self.filter_fields = {}

        self.set_search_and_filter_fields_for_indexed_fields(self.model, index_columns)
        self.search_fields = tuple(self.search_fields)

    def set_search_and_filter_fields_for_indexed_fields(self, model, index_columns):
        """
        For all indexed fields, append to search_fields and set filter_fields.
        :param model: The Django model class to inspect.
        :param index_columns: A list of indexed column names.
        """
        # Loop through all of the fields. If the field is indexed, add it
        # to the allowed filter columns. Additionally, if it is a text type,
        # add it to the searchable columns for the data browser.
        for field in model._meta.get_fields():
            if field.name in index_columns:
                field_type = field.get_internal_type()
                if field_type in ("CharField", "TextField"):
                    # Add column to searchable fields, with 'starts with' search ('^')
                    # See: http://www.django-rest-framework.org/api-guide/filtering/#searchfilter  # noqa
                    self.search_fields.append(f"^{field.name}")

                    # Add column to filterable fields with all search options
                    self.filter_fields[field.name] = [
                        "exact",
                        "in",
                        "contains",
                        "startswith",
                        "endswith",
                    ]
                elif field_type in (
                    "IntegerField",
                    "BigIntegerField",
                    "DecimalField",
                    "FloatField",
                ):
                    # Add column to filterable fields with all search options
                    self.filter_fields[field.name] = [
                        "exact",
                        "in",
                        "lt",
                        "lte",
                        "gt",
                        "gte",
                    ]
                elif field_type in ("DateField", "DateTimeField", "TimeField"):
                    # Add column to filterable fields with all search options
                    self.filter_fields[field.name] = [
                        "exact",
                        "in",
                        "lt",
                        "lte",
                        "gt",
                        "gte",
                        "range",
                    ]

    def get_pagination_class(self):
        """
        Grab the estimated count from the query plan; if its a large table,
        use the count estimate for Pagination instead of an exact count.
        :return: CountEstimatePagination if the table is large, otherwise None
        """
        table_estimate_count = estimate_count(
            self.db_name, f"SELECT * FROM {self.schema_name}.{self.table_name}"
        )
        if table_estimate_count > self.get_estimate_count_limit():
            return CountEstimatePagination
        return None

    def get_queryset(self):
        """
        Use the db_name set when the API is built.
        """
        # If we're using the ComplexFilterBackend, it supercedes the
        # RestFrameworkFilterBackend; trigger from the URL parameter.
        if "filters" in self.request.query_params:
            if ComplexFilterBackend not in self.filter_backends:
                self.filter_backends += [ComplexFilterBackend]
            if RestFrameworkFilterBackend in self.filter_backends:
                self.filter_backends.remove(RestFrameworkFilterBackend)

        queryset = self.model.objects.using(self.db_name).all()

        return queryset

    def get_serializer_class_name(self):
        """
        Returns the full path to the serializer class.
        """
        return "rest_framework.serializers.ModelSerializer"

    def get_serializer_class(self):
        """
        Overrides Django REST Framework to dynamically create the serializer,
        by importing the serializer, setting the model, and allowing all
        fields.
        """
        parts = self.get_serializer_class_name().split(".")
        module = parts.pop()
        path = ".".join(parts)

        APISerializer = getattr(
            import_module(path),
            module,
        )

        class GenericSerializer(APISerializer):
            """
            Placeholder for the serializer we will create dynamically below.
            """

            class Meta:
                model = self.model
                fields = "__all__"

        return GenericSerializer

    def get_permission(self):
        """
        If overridden, this method must provide a valid Django REST Framework
        permission class to use in the view.
        """
        return None

    def get_estimate_count_limit(self):
        """
        If overridden, this method returns the number of rows in a query planner
        estimate count which will cause estimated row counts to be used instead
        of the (much) slower `SELECT COUNT(*)` method. We'll start at one million.
        """
        return 999_999

    def get_indexes(self):
        """
        Return a list of unique columns that are part of an index on a table
        by providing schema name and table name.
        """

        index_columns = []

        cursor = connections[self.db_name].cursor()
        cursor.execute(
            self.index_sql,
            {"schema_name": self.schema_name, "table_name": self.table_name},
        )
        rows = cursor.fetchall()

        for row in rows:
            column_name, _ = reserved_word_check(row[0])
            index_columns.append(column_name)

        return index_columns

    def get_positions(self):
        """
        Return a dict of keyed column names and their ordinal positions as values.
        """

        positions = {}

        cursor = connections[self.db_name].cursor()
        cursor.execute(
            """
            SELECT column_name, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = %(table_schema)s
            AND table_name = %(table_name)s
            """,
            {"table_schema": self.schema_name, "table_name": self.table_name},
        )

        for row in cursor.fetchall():
            column_name, _ = reserved_word_check(row[0])
            positions[column_name] = row[1]

        return positions
