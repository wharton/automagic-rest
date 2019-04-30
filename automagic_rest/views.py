from importlib import import_module

from django.db import connections

from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework_filters.backends import (
    ComplexFilterBackend,
    RestFrameworkFilterBackend,
)

from .pagination import estimate_count, CountEstimatePagination


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


class GenericViewSet(ReadOnlyModelViewSet):
    """
    """

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
        self.db_name, self.python_path_name, self.schema_name, self.table_name = split_basename(
            self.basename
        )

        self.model = getattr(
            import_module(f"{self.python_path_name}.models.{self.schema_name}"),
            f"{self.schema_name}_{self.table_name}_model",
        )
        api_permission = self.get_permission()

        # Grab the estimated count from the query plan; if its a large table,
        # use the count estimate for Pagination instead of an exact count.
        table_estimate_count = estimate_count(
            self.db_name, f"SELECT * FROM {self.schema_name}.{self.table_name}"
        )
        if table_estimate_count > self.get_estimate_count_limit():
            self.pagination_class = CountEstimatePagination

        # Only override permissions if provided.
        if api_permission:
            self.permission_classes = (api_permission,)

        self.filter_backends = (OrderingFilter, SearchFilter)
        self.ordering_fields = "__all__"
        self.search_fields = []

        # Add any columns indexed in the PostgreSQL database to be
        # filterable columns in the API
        index_columns = self.get_indexes()

        # If any columns are indexed, add the appropriate filter backends
        # and set up a dictionary of filter fields
        if len(index_columns):
            self.filter_backends = self.filter_backends + (
                RestFrameworkFilterBackend,
                ComplexFilterBackend,
            )
            self.filter_fields = {}

        # Loop through all of the fields. If the field is indexed, add it
        # to the allowed filter columns. Additionally, if it is a text type,
        # add it to the searchable columns for the data browser.
        for field in self.model._meta.get_fields():
            if field.name in index_columns:
                field_type = field.get_internal_type()
                if field_type in ("CharField", "TextField"):
                    # Add column to searchable fields, with 'starts with' search ('^')
                    # See: http://www.django-rest-framework.org/api-guide/filtering/#searchfilter
                    self.search_fields.append(f"^{field.name}")

                    # Add column to filterable fields with all search options
                    self.filter_fields[field.name] = [
                        "exact",
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
                    self.filter_fields[field.name] = ["exact", "lt", "lte", "gt", "gte"]
                elif field_type in ("DateField", "DateTimeField", "TimeField"):
                    # Add column to filterable fields with all search options
                    self.filter_fields[field.name] = ["exact", "lt", "lte", "gt", "gte"]

        self.search_fields = tuple(self.search_fields)

    def get_queryset(self):
        """
        Use the db_name set when the API is built.
        """
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
        of the (much) slowed `SELECT COUNT(*)` method. We'll start at one million.
        """
        return 999_999

    def get_indexes(self):
        """
        Return a list of unique columns that are part of an index on a table
        by providing schema name and table name.
        """

        cursor = connections[self.db_name].cursor()

        cursor.execute(
            self.index_sql, {"schema_name": self.schema_name, "table_name": self.table_name}
        )

        rows = cursor.fetchall()

        index_columns = []

        for row in rows:
            index_columns.append(row[0])

        return index_columns
