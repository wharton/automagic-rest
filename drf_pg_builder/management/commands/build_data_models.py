from collections import namedtuple, OrderedDict

from glob import glob
from os import remove
from re import sub

from django.core.management.base import BaseCommand
from django.db import connections
from django.template.loader import render_to_string

# Map PostgreSQL column types to Django ORM field type
# Please note: "blank=True, null=True" must be typed
# exactly, as it will be stripped out for primary keys
# The first column in the table is always marked as the
# primary key.
COLUMN_FIELD_MAP = {
    'smallint': 'IntegerField({}blank=True, null=True{})',
    'integer': 'IntegerField({}blank=True, null=True{})',
    'bigint': 'BigIntegerField({}blank=True, null=True{})',

    'numeric': 'DecimalField({}blank=True, null=True{})',
    'double precision': 'FloatField({}blank=True, null=True{})',

    'date': 'DateField({}blank=True, null=True{})',
    'timestamp without time zone': 'DateTimeField({}blank=True, null=True{})',
    'time without time zone': 'TimeField({}blank=True, null=True{})',

    'character varying': 'TextField({}blank=True, null=True{})',
}

# Python reserved words list
# These can not be made into field names; we will append
# `_var` to any fields with these names.
RESERVED_WORDS = [
    'False',
    'None',
    'True',
    'and',
    'as',
    'assert',
    'async',
    'await',
    'break',
    'class',
    'continue',
    'def',
    'del',
    'elif',
    'else',
    'except',
    'finally',
    'for',
    'from',
    'global',
    'if',
    'import',
    'in',
    'is',
    'lambda',
    'nonlocal',
    'not',
    'or',
    'pass',
    'raise',
    'return',
    'try',
    'while',
    'with',
    'yield',
]

# Additional words DRF needs
RESERVED_WORDS.append(
    'format',
)


def fetch_result_with_blank_row(cursor):
    """
    Gets all the rows, and appends a blank row so that the final
    model and column are written in the loop.
    """
    results = cursor.fetchall()
    results.append(
        ('__FALSY__', '__FALSY__', '__FALSY__', 'integer', '__FALSY__')
    )
    desc = cursor.description
    nt_result = namedtuple('Result', [col[0] for col in desc])

    return [nt_result(*row) for row in results]


class Command(BaseCommand):
    """
    This command will create Django models by introspecting the PostgreSQL data.
    Why not use inspectdb? It doesn't have enough options; this will be broken
    down by schema / product.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            '--database',
            action='store',
            dest='database',
            default="pgdata",
            help='The database to use. Defaults to the "pgdata" database.'
        )
        parser.add_argument(
            '--schema',
            action='store',
            dest='schema',
            default="",
            help='A specific product to remodel, by schema name from PostgreSQL. Omit for all.'
        )
        parser.add_argument(
            '--owner',
            action='store',
            dest='owner',
            default="wrdsadmn",
            help='Select schemata from this PostgreSQL owner user. Defaults to the "wrdsadmn" owner.'
        )
        parser.add_argument(
            '--path',
            action='store',
            dest='path',
            default="data",
            help='The path where to place the model and serializer files.',
        )

    def connect_cursor(self, options, db=None):
        """
        Returns a cursor for a database defined in Django's settings.
        """

        # Get the database we're working with from options if it isn't passed implicitly
        if db is None:
            db = options.get('database')
        connection = connections[db]

        cursor = connection.cursor()

        return cursor

    def get_allowed_schemata(self, options, cursor):
        """
        Method which returns a list of schemata allows to be built into endpoints.

        If None, allows all schemata to be built.
        """
        return None

    def get_serializer(self):
        """
        Returns the path to the serializer to be used.
        """
        return "rest_framework.serializers.ModelSerializer"

    def sanitize_sql_identifier(self, identifier):
        """
        PG schemata should only contain alphanumerics and underscore.
        """
        return sub('[^0-9a-zA-Z]+', '_', identifier)

    def metadata_sql(self, schema_sql, allowed_schemata_sql):
        return f"""
            SELECT s.schema_name, c.table_name, c.column_name, c.data_type, c.character_maximum_length

            FROM information_schema.schemata s

            INNER JOIN information_schema.columns c
            ON s.schema_name = c.table_schema

            WHERE s.schema_owner = %(schema_owner)s
            AND c.table_name NOT LIKE '%%chars'
            {schema_sql}
            {allowed_schemata_sql}

            ORDER BY s.schema_name, c.table_name, c.column_name
        """

    def get_endpoint_metadata(self, options, cursor):
        schema = options.get('schema')
        owner = options.get('owner')

        allowed_schemata = self.get_allowed_schemata(options, cursor)

        allowed_schemata_sql = ""
        if allowed_schemata:
            allowed_schemata_sql = f"""AND s.schema_name IN ('{"', '".join(allowed_schemata)}')"""

        schema_sql = ""
        if len(schema):
            schema = self.sanitize_sql_identifier(schema)

            if schema in allowed_schemata:
                schema_sql = f"AND s.schema_name = '{schema}'"
            else:
                print("WARNING! The product you specified isn't in the WRDS product list. Running all endpoints.")

        sql = self.metadata_sql(schema_sql, allowed_schemata_sql)
        cursor.execute(
            sql,
            {
                "schema_owner": owner,
            }
        )

        rows = fetch_result_with_blank_row(cursor)

        return rows

    def delete_generated_files(self, root_path):
        """
        Removes the previously generated files so we can recreate them.
        """
        for path in ('models', 'serializers'):
            files_to_delete = glob(f'{root_path}/{path}/*.py')
            for f in files_to_delete:
                if not f.endswith('__.py'):
                    remove(f)

    def write_schema_files(self, root_path, context):
        """
        Write out the current schema model and serializer.
        """
        for output_file in ("models", "serializers"):
            with open(
                f"""{root_path}/{output_file}/{context["schema_name"]}.py""",
                "w",
            ) as f:
                output = render_to_string(f"drf_pg_builder/{output_file}.html", context)
                f.write(output)

    def handle(self, *args, **options):
        # model_count = 0

        root_path = options.get('path')

        if len(options.get("schema", "")) == 0:
            self.delete_generated_files(root_path)

        cursor = self.connect_cursor(options)

        # Get the metadata given the options from PostgreSQL
        print("Getting the metadata from PostgreSQL...")
        schemata_data = self.get_endpoint_metadata(options, cursor)

        # Get the serializer from the path
        serializer_data = self.get_serializer().split(".")

        # Initial context. Set up so it doesn't try to write on the first
        # pass through
        context = {
            "schema_name": None,
            "serializer": serializer_data.pop(),
            "serializer_path": ".".join(serializer_data),
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
                if row.schema_name != "__FALSY__":
                    print(f"*** Working on schema: {row.schema_name} ***")
                context["schema_name"] = row.schema_name
                context["tables"] = {}

            if row.table_name not in context["tables"]:
                model_count += 1
                if row.schema_name != "__FALSY__":
                    print(f"{model_count}: {row.table_name}")
                context["tables"][row.table_name] = []
                primary_key_has_been_set = False
                context["routes"].append(
                    f"""{row.schema_name}.{row.table_name}"""
                )

            # If the column name is a Python reserved word, append an underscore
            # to follow the Python convention
            if row.column_name in RESERVED_WORDS or row.column_name.endswith('_'):
                if row.column_name.endswith('_'):
                    under_score = ''
                else:
                    under_score = '_'
                column_name = '{}{}var'.format(
                    row.column_name,
                    under_score,
                )
                db_column = ", db_column='{}'".format(row.column_name)
            else:
                column_name = row.column_name
                db_column = ''

            if(primary_key_has_been_set):
                field_map = COLUMN_FIELD_MAP[row.data_type].format('', db_column)
            else:
                # We'll make the first column the primary key, since once is required in the Django ORM
                # and this is read-only. Primary keys can not be set to NULL in Django.
                field_map = COLUMN_FIELD_MAP[row.data_type].format('primary_key=True', db_column).replace('blank=True, null=True', '')
                primary_key_has_been_set = True

            context["tables"][row.table_name].append(
                f"""{column_name} = models.{field_map}"""
            )

        # Pop off the final false row, and write the URLs file.
        context["routes"].pop()
        with open(f"{root_path}/urls.py", "w") as f:
            output = render_to_string(f"drf_pg_builder/urls.html", context)
            f.write(output)
