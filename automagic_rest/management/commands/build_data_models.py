from collections import namedtuple

from glob import glob
import os
from re import sub

from django.core.management.base import BaseCommand
from django.db import connections
from django.template.loader import render_to_string

from automagic_rest.settings import get_reserved_words_to_append_underscore

# Map PostgreSQL column types to Django ORM field type
# Please note: "blank=True, null=True" must be typed
# exactly, as it will be stripped out for primary keys
# The first column in the table is always marked as the
# primary key.
COLUMN_FIELD_MAP = {
    "smallint": "IntegerField({}blank=True, null=True{})",
    "integer": "IntegerField({}blank=True, null=True{})",
    "bigint": "BigIntegerField({}blank=True, null=True{})",
    "oid": "BigIntegerField({}blank=True, null=True{})",
    "boolean": "BooleanField({}blank=True, null=True{})",
    "numeric": "DecimalField({}blank=True, null=True{})",
    "double precision": "FloatField({}blank=True, null=True{})",
    "real": "FloatField({}blank=True, null=True{})",
    "date": "DateField({}blank=True, null=True{})",
    "timestamp with time zone": "DateTimeField({}blank=True, null=True{})",
    "timestamp without time zone": "DateTimeField({}blank=True, null=True{})",
    "time with time zone": "TimeField({}blank=True, null=True{})",
    "time without time zone": "TimeField({}blank=True, null=True{})",
    "character": "TextField({}blank=True, null=True{})",
    "character varying": "TextField({}blank=True, null=True{})",
    "text": "TextField({}blank=True, null=True{})",
    "uuid": "UUIDField({}blank=True, null=True{})",
    "interval": "DurationField({}blank=True, null=True{})",
    "json": "JSONField({}blank=True, null=True{})",
    "jsonb": "JSONField({}blank=True, null=True{})",
}

# Words that can't be used as column names
RESERVED_WORDS = get_reserved_words_to_append_underscore()


def fetch_result_with_blank_row(cursor):
    """
    Gets all the rows, and appends a blank row so that the final
    model and column are written in the loop.
    """
    results = cursor.fetchall()
    results.append(
        ("__BLANK__", "__BLANK__", "__BLANK__", "integer", "__BLANK__", 0, 0)
    )
    desc = cursor.description
    nt_result = namedtuple("Result", [col[0] for col in desc])

    return [nt_result(*row) for row in results]


class Command(BaseCommand):
    """
    This command will create Django models by introspecting the PostgreSQL data.
    Why not use inspectdb? It doesn't have enough options; this will be broken
    down by schema / product.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            action="store",
            dest="database",
            default="my_pg_data",
            help='The database to use. Defaults to the "my_pg_data" database.',
        )
        parser.add_argument(
            "--owner",
            action="store",
            dest="owner",
            default="my_pg_user",
            help=(
                'Select schemata from this PostgreSQL owner user. Defaults to the '
                '"wrdsadmn" owner.'
            ),
        )
        parser.add_argument(
            "--path",
            action="store",
            dest="path",
            default="data_path",
            help="The path where to place the model files.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            dest="verbose",
            default=False,
            help=(
                "Sets verbose mode; displays each model built, instead of just "
                "schemata."
            ),
        )

    def get_db(self, options):
        """
        Returns the Django name of the PostgreSQL database we will connect to.
        """
        return options.get("database")

    def connect_cursor(self, options, db=None):
        """
        Returns a cursor for a database defined in Django's settings.
        """

        if db is None:
            db = self.get_db(options)
        connection = connections[db]

        cursor = connection.cursor()

        return cursor

    def get_root_python_path(self, options):
        """
        Returns the root Python path where we will build the API.
        """
        return options.get("path")

    def get_view(self):
        """
        Returns the path to the view to be used.
        """
        return "automagic_rest.views.GenericViewSet"

    def get_router(self):
        """
        Returns the path to the router to be used.
        """
        return "rest_framework.routers.DefaultRouter"

    def get_max_digits_default(self):
        """
        Returns the default max_digits for a numeric field
        where they are not explicitly set in PostgreSQL.
        """
        return 100

    def get_decimal_places_default(self):
        """
        Returns the default decimal_places for a numeric field
        where they are not explicitly set in PostgreSQL.
        """
        return 25

    def sanitize_sql_identifier(self, identifier):
        """
        PG schemata should only contain alphanumerics and underscore.
        """
        return sub("[^0-9a-zA-Z]+", "_", identifier)

    def metadata_sql(self, allowed_schemata_sql, extra_sql):
        """
        Returns the SQL to pull the introspection metadata.
        """
        return f"""
            SELECT s.schema_name, c.table_name, c.column_name, c.data_type,
            c.character_maximum_length, c.numeric_precision, c.numeric_scale

            FROM information_schema.schemata s

            INNER JOIN information_schema.columns c
            ON s.schema_name = c.table_schema

            WHERE s.schema_owner = %(schema_owner)s
            {allowed_schemata_sql}
            {extra_sql}

            ORDER BY s.schema_name, c.table_name, c.column_name
        """

    def get_allowed_schemata(self, options, cursor):
        """
        Method which returns a list of schemata allows to be built into endpoints.

        If None, allows all schemata to be built.
        """
        return None

    def get_allowed_schemata_sql(self, allowed_schemata):
        """
        Transforms the list of allowed schemata into SQL for the query.
        """
        allowed_schemata_sql = ""
        if allowed_schemata:
            allowed_schemata_sql = (
                f"""AND s.schema_name IN ('{"', '".join(allowed_schemata)}')"""
            )

        return allowed_schemata_sql

    def get_extra_sql(self):
        """
        Blank stub which allows adding extra SQL to the query against the information
        schema.
        """
        return ""

    def get_owner(self, options):
        """
        Returns the PostgreSQL DB user that owns the schemata to be
        processed.
        """
        return options.get("owner")

    def get_endpoint_metadata(self, options, cursor):
        owner = self.get_owner(options)

        allowed_schemata = self.get_allowed_schemata(options, cursor)
        allowed_schemata_sql = self.get_allowed_schemata_sql(allowed_schemata)
        extra_sql = self.get_extra_sql()

        sql = self.metadata_sql(allowed_schemata_sql, extra_sql)
        cursor.execute(sql, {"schema_owner": owner})

        rows = fetch_result_with_blank_row(cursor)

        return rows

    def delete_generated_files(self, root_path):
        """
        Removes the previously generated files so we can recreate them.
        """
        files_to_delete = glob(f"{root_path}/models/*.py")
        for f in files_to_delete:
            if not f.endswith("__.py"):
                os.remove(f)

    def write_schema_files(self, root_path, context):
        """
        Write out the current schema model.
        """
        with open(
            f"""{root_path}/models/{context["schema_name"]}.py""", "w"
        ) as f:
            output = render_to_string("automagic_rest/models.html", context)
            f.write(output)

    def handle(self, *args, **options):
        verbose = options.get("verbose")
        max_digits_default = self.get_max_digits_default()
        decimal_places_default = self.get_decimal_places_default()
        # Get the provided root path and create directories
        root_python_path = self.get_root_python_path(options)
        root_path = root_python_path.replace(".", os.sep)
        os.makedirs(root_path + os.sep + "models", exist_ok=True)

        if len(options.get("schema", "")) == 0:
            self.delete_generated_files(root_path)

        cursor = self.connect_cursor(options)

        # Get the metadata given the options from PostgreSQL
        print("Getting the metadata from PostgreSQL...")
        schemata_data = self.get_endpoint_metadata(options, cursor)

        # Get the view, and router data from the full path
        view_data = self.get_view().split(".")
        router_data = self.get_router().split(".")

        # Initial context. Set up so it doesn't try to write on the first
        # pass through
        context = {
            "db_name": self.get_db(options),
            "schema_name": None,
            "root_python_path": root_python_path,
            "view": view_data.pop(),
            "view_path": ".".join(view_data),
            "router": router_data.pop(),
            "router_path": ".".join(router_data),
            "routes": [],
        }
        model_count = 0

        for row in schemata_data:
            if context["schema_name"] != row.schema_name:
                # We're on a new schema. Write the previous, unless it
                # is our first time through.
                if context["schema_name"]:
                    self.write_schema_files(root_path, context)

                # Set the new schema name, clear the tables and columns
                if row.schema_name != "__BLANK__":
                    print(f"*** Working on schema: {row.schema_name} ***")
                context["schema_name"] = row.schema_name
                context["tables"] = {}

            if row.table_name not in context["tables"]:
                model_count += 1
                if row.schema_name != "__BLANK__" and verbose:
                    print(f"{model_count}: {row.table_name}")
                context["tables"][row.table_name] = []
                primary_key_has_been_set = False
                context["routes"].append(f"""{row.schema_name}.{row.table_name}""")

            # If the column name is a Python reserved word, append an underscore
            # to follow the Python convention
            if row.column_name in RESERVED_WORDS:
                column_name = f"{row.column_name}_"
                db_column = ", db_column='{}'".format(row.column_name)
            else:
                column_name = row.column_name
                db_column = ""

            # For decimals, add the max_length and decimal places
            if row.data_type == "numeric":
                max_digits = row.numeric_precision
                if max_digits is None:
                    max_digits = max_digits_default

                decimal_places = row.numeric_scale
                if decimal_places is None:
                    decimal_places = decimal_places_default

                db_column += (
                    f", max_digits={max_digits}, decimal_places={decimal_places}"
                )

            if row.data_type in COLUMN_FIELD_MAP:
                if primary_key_has_been_set:
                    field_map = COLUMN_FIELD_MAP[row.data_type].format("", db_column)
                else:
                    # We'll make the first column the primary key, since once is
                    # required in the Django ORM and this is read-only. Primary keys can
                    # not be set to NULL in Django.
                    field_map = (
                        COLUMN_FIELD_MAP[row.data_type]
                        .format("primary_key=True", db_column)
                        .replace("blank=True, null=True", "")
                    )
                    primary_key_has_been_set = True
            else:
                print(
                    f"WARNING: skipping column {row.column_name} of unknown data type "
                    f"{row.data_type}."
                )

            context["tables"][row.table_name].append(
                f"""{column_name} = models.{field_map}"""
            )

        # Pop off the final false row, and write the URLs file.
        context["routes"].pop()
        with open(f"{root_path}/urls.py", "w") as f:
            output = render_to_string("automagic_rest/urls.html", context)
            f.write(output)
