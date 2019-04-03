from collections import OrderedDict
from glob import glob
from os import remove
from re import sub

from django.core.management.base import BaseCommand
from django.db import connections

from inflection import camelize

SCHEMA_OWNER = 'wrdsadmn'

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
            '--product',
            action='store',
            dest='product',
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

    def get_endpoint_metadata(self, options, cursor):
        product = options.get('product')
        owner = options.get('owner')

        # Get the list of products from SQL Server
        ms_cursor = self.connect_cursor(options, 'mssqlwrds')
        res = ms_cursor.execute(
            """
            SELECT REPLACE(product, '.', '_') AS schema_name FROM wrds_products ORDER BY product
            """
        )
        rows = res.fetchall()

        wrds_product_list = []

        for row in rows:
            wrds_product_list.append(f"'{row[0]}'")

        product_sql = ""
        if len(product):
            # PG schemata should only contain alphanumerics and underscore
            product = sub('[^0-9a-zA-Z]+', '_', product)
            if product in wrds_product_list:
                product_sql = f"AND s.schema_name = '{product}'"
            else:
                print("WARNING! The product you specified isn't in the WRDS product list. Running all endpoints.")

            sql = f"""
                SELECT s.schema_name, c.table_name, c.column_name, c.data_type, c.character_maximum_length

                FROM information_schema.schemata s

                INNER JOIN information_schema.columns c
                ON s.schema_name = c.table_schema

                WHERE s.schema_owner = %(schema_owner)s
                AND s.schema_name = %(schema_name)s
                {product_sql}
                AND s.schema_name IN ({', '.join(wrds_product_list)})
                AND c.table_name NOT LIKE '%%chars'

                ORDER BY s.schema_name, c.table_name, c.column_name
            """

            cursor.execute(
                sql,
                {
                    "schema_owner": owner,
                    "schema_name": product,
                }
            )
        else:
            sql = f"""
                SELECT s.schema_name, c.table_name, c.column_name, c.data_type, c.character_maximum_length

                FROM information_schema.schemata s

                INNER JOIN information_schema.columns c
                ON s.schema_name = c.table_schema

                WHERE s.schema_owner = %(schema_owner)s
                AND s.schema_name IN ({', '.join(wrds_product_list)})
                AND c.table_name NOT LIKE '%%chars'

                ORDER BY s.schema_name, c.table_name, c.column_name
            """

            cursor.execute(
                sql,
                {
                    "schema_owner": owner,
                }
            )

        rows = cursor.fetchall()

        return rows

    def get_friendly_schemata(self, options, cursor):
        product = options.get('product')

        if len(product):
            cursor.execute(
                """
                SELECT DISTINCT frname AS schema_name
                FROM wrds_lib_internal.friendly_schema_mapping
                WHERE frname = %(schema_name)s
                ORDER BY schema_name
                """,
                {
                    "schema_name": product,
                }
            )
        else:
            cursor.execute(
                """
                SELECT DISTINCT frname AS schema_name
                FROM wrds_lib_internal.friendly_schema_mapping
                ORDER BY schema_name
                """
            )

        rows = cursor.fetchall()

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

    def handle(self, *args, **options):
        model_count = 0

        for root_path in ('data', 'data_full',):
            if len(options.get('product')) == 0:
                self.delete_generated_files(root_path)

            cursor = self.connect_cursor(options)

            if root_path == 'data':
                schema_rows = self.get_friendly_schemata(options, cursor)
            elif root_path == 'data_full':
                schema_rows = self.get_schemata(options, cursor)
            else:
                raise ValueError(
                    'Invalid value for "root_path" set in build script: "{}"'.format(
                        root_path,
                    )
                )
            print(
                'COUNT {}: {}'.format(
                    root_path,
                    len(schema_rows),
                )
            )

            url_import_dict = OrderedDict()

            for schema_row in schema_rows:
                model_file_content = "from django.db import models\n"

                serializer_file_content = "from home.serializers import DynamicFieldsModelSerializer\n\n"
                table_import_list = []
                serializer_content = ''

                schema_name = schema_row[0]
                url_import_dict[schema_name] = []

                print('*** Working on product: {} ***'.format(schema_name))

                table_rows = self.get_tables(cursor, schema_name)
                for table_row in table_rows:
                    table_name = table_row[0]
                    model_count += 1
                    print(
                        'Model {}: {}'.format(
                            model_count,
                            table_name,
                        )
                    )
                    table_name_camelize = camelize('{0}_{1}'.format(schema_name, table_name))
                    model_content = 'class {}Model(models.Model):\n'.format(table_name_camelize)

                    # Keep track of the Model names we'll need to insert into Serializers and Views
                    table_import_list.append(table_name_camelize)

                    # Keep track of the elements we'll need to do imports and registers in the URLs file
                    url_import_dict[schema_name].append((table_name, table_name_camelize))

                    # Blank list for keeping track of fields for the Serializer
                    serializer_field_list = []

                    # Track is a field has been set as primary key
                    primary_key_has_been_set = 0

                    column_rows = self.get_columns(cursor, schema_name, table_name)
                    for column_row in column_rows:
                        # Check to see if column length is populated;
                        # If it isn't, set to unlimited max_length
                        """
                        if column_row[3] is None:
                            max_length = "-1"
                        else:
                            max_length = column_row[3]
                        """

                        # If the column name is a Python reserved word, append an underscore
                        # to follow the Python convention
                        if column_row[1] in RESERVED_WORDS or column_row[1].endswith('_'):
                            if column_row[1].endswith('_'):
                                under_score = ''
                            else:
                                under_score = '_'
                            column_name = '{}{}var'.format(
                                column_row[1],
                                under_score,
                            )
                            db_column = ", db_column='{}'".format(column_row[1])
                        else:
                            column_name = column_row[1]
                            db_column = ''

                        if(primary_key_has_been_set):
                            field_map = COLUMN_FIELD_MAP[column_row[2]].format('', db_column)
                        else:
                            # We'll make the first column the primary key, since once is required in the Django ORM
                            # and this is read-only. Primary keys can not be set to NULL in Django.
                            field_map = COLUMN_FIELD_MAP[column_row[2]].format('primary_key=True', db_column).replace('blank=True, null=True', '')
                            primary_key_has_been_set = 1

                        model_content += '    {} = models.{}\n'.format(
                            column_name,
                            field_map,
                        )
                        serializer_field_list.append("'{}'".format(column_row[1]))

                    # Append the Model file content with the information for this table from PostgreSQL
                    model_file_content += f"""

{model_content}
    class Meta:
        managed = False
        db_table = '{schema_name}\\".\\"{table_name}'
"""

                    # Append the Serializer for this Model to be injected into the Serialize file
                    serializer_content += f"""
class {table_name_camelize}Serializer(DynamicFieldsModelSerializer):
    class Meta:
        model = {table_name_camelize}Model
        fields = '__all__'

"""

                # Append a blank field to the table_import_list so formatting
                # works correctly and there is a final comma.
                table_import_list.append('')

                serializer_file_content += """from ..models.{0} import (
    {1}
)

{2}""".format(
                    schema_name,
                    'Model,\n    '.join(table_import_list),
                    serializer_content,
                )

                with open(f'{root_path}/models/{schema_name}.py', 'w') as f:
                    f.write(model_file_content)
                with open(f'{root_path}/serializers/{schema_name}.py', 'w') as f:
                    f.write(serializer_file_content)

            # Build urls.py file for all datasets
            url_file_register = ''

            for schema, table_items in url_import_dict.items():
                if table_items:
                    for table_item in table_items:
                        url_file_register += "router.register(r'{0}.{1}', GenericViewSet, base_name='{0}-{1}')\n".format(
                            schema,
                            table_item[0],
                        )
                else:
                    print('WARNING: The schema "{}" has no tables.'.format(schema))

            url_file_content = """from django.urls import include, re_path

from home.routers import PermittedRouter

from {}.views import GenericViewSet

router = PermittedRouter()
{}

urlpatterns = [
    re_path(r'^', include(router.urls)),
]
""".format(
                root_path,
                url_file_register,
            )

            with open('{}/urls.py'.format(root_path), 'w') as f:
                f.write(url_file_content)
