# Automagic REST

[![pypi](https://img.shields.io/pypi/v/automagic-rest.svg)](https://pypi.python.org/pypi/automagic-rest/)

Automagic REST is a code generator which builds a full Django app as a Django REST Framework read-only environment for a set of tables in a PostgreSQL database.

This is very much for a specific niche, but we have found it quite powerful for building a RESTful API on top of datasets we receive from other sources through introspection of PostgreSQL's `information_schema`.

## Installation

To get started, `pip install automagic-rest` and add `automagic_rest` to your `INSTALLED_APPS` setting in Django.

## Configuration and Customization

Setting up a secondary database in Django is recommended. For the following examples, we'll set up one called `my_pg_data` with the user `my_pg_user`:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'pg_web_db',
        'USER': 'web_user',
        'PASSWORD': '',
        'HOST': 'pg-web.domain.com',
    },
    'my_pg_data': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'pg_data_db',
        'USER': 'my_pg_user',
        'PASSWORD': '',
        'HOST': 'pg-data.domain.com',
    },
}
```

By default, Automagic REST will create a directory called `data_path` at the root of your Django project, where `manage.py` lives. The follow options can be passed to the command:

* `--database` (default: `my_pg_data`): the name of the Django database as defined in the `DATABASES` setting.
* `--owner` (default: `my_pg_user`): the name of the PostgreSQL user which owns the schemata to be processed. This will normally be the same as the `USER` in the `DATABASES` setting for the database above.
* `--path` (default: `data_path`): the path to write the models and serializers to. This path will be completely deleted and rewritten whenever the command is run, so be careful!

Example: `python manage.py build_data_models --database=my_data --owner=my_user --path=my_data_path`

Methods are provided which can be overridden to customize the endpoint with your own Django management command.

### class automagic_rest.management.commands.build_data_models.Command

`get_db` (default: `my_pg_data`): the name of the PostgreSQL database in Django's settings that we will introspect to build the API.

`get_owner` (default: `my_pg_user`): the name of the PostgreSQL user that owns the schemata we will introspect.

`get_allowed_schemata` (default: `None`): if set, returns a list of schemata in the database to be built. If `None`, selects all schemata for the specific user.

`get_extra_sql` (default: `""`): if set, appends the SQL returned by this method to
the information schema query. Useful for exclusions.

`get_root_python_path` (default: `data_path`): a Python path where you would like to write the models, serializers, and routes. **IMPORTANT**: this path will be wiped and re-written every time the build command is run. It should be a dedicated directory with nothing else in it.

`get_view` (default: `automagic_rest.views.GenericViewSet`): the view to use.

`get_router` (default: `rest_framework.routers.DefaultRouter`): the router to use.

`get_max_digits_default` (default: 100): the number of `max_digits` to provide for `NUMERIC` field types that are not explicitly set in PostgreSQL.

`get_decimal_places_default` (default: 25): the number of `decimal_places` to provide for `NUMERIC` field types that are not explicitly set in PostgreSQL.

`sanitize_sql_identifier`: this method takes a string, and sanitizes it for injections into SQL, allowing only alphanumerics and underscores.

`metadata_sql`: this method returns the SQL used to pull the metadata from PostgreSQL to build the endpoints.

To customize the build command, here is an example:

```python
# my_app/home/management/commands/my_build_data_models.py
from automagic_rest.management.commands import build_data_models


class Command(build_data_models.Command):
    """
    My specific overrides for DRF PG Builder command.
    """

    def get_db(self, options):
        """
        Returns our customized Django DB name.
        """
        return "my_data"

    def get_owner(self, options):
        """
        Returns our customized schema owner.
        """
        return "my_user"

    def get_root_python_path(self, options):
        """
        Returns our customized build path.
        """
        return "my_data_path"

    def get_view(self):
        """
        Returns our customized view path.
        """
        return "my_app.views.MyDataViewSet"

    def get_allowed_schemata(self, options, cursor):
        """
        Return a list of allowed schemata we want to create RESTful
        endpoints for. If None, will create endpoints for all schemata
        owned by the schema owner user.
        """
        allowed_schemata = ['my_data', 'public_data']

        return allowed_schemata
    
    def get_extra_sql(self):
        """
        Returns SQL to append to the information schema query.

        In this example, we exclude any tables ending in "_old".
        """
        return """
            AND c.table_name NOT LIKE '%%_old'
        """
```

### Python Reserved Words and Underscores

`AUTOMAGIC_REST_RESERVED_WORD_SUFFIX` is an available Django setting, defaulting to `var`. Make sure this value does not start or end in an underscore, or it will circumvent the fix (this is prevent double underscores in field names, which are used as separators). Python reserved words and fields ending in an underscore will have this value appended to their Django model field name:

* Python reserved words example: `for` -> `forvar`
* Columns ending in an underscore example: `date_` -> `date_var`.

### class views.GenericViewSet

The view has several methods and attributes which can be overridden as well.

#### Attributes

`index_sql`: this attribute defines SQL to return the first column in each index for the current table for the Model. These will be used to dynamically make all indexed fields searchable and filterable.

#### Methods

`get_serializer_class_name` (default: `rest_framework.serializers.ModelSerializer`): the full path of the serializer class to use.

`get_permission` (default: `None`): returns a permission class to use for the endpoint. When left at the default of `None`, uses the default permission class set by Django REST Framework.

`get_estimate_count_limit` (default: `999_999`): to prevent long-running `SELECT COUNT(*)` queries, the view estimates the number of rows in the table by examing the query plan. If greater than this number, it will estimate pagination counts for vastly improved speed.

To follow on the example above, here is an example of an overridden view, which sets the permission type and includes a mixin for naming Excel file downloads:

```python
from rest_framework.permissions import IsAuthenticated
from drf_excel.mixins import XLSXFileMixin

class MyGenericViewSet(XLSXFileMixin, GenericViewSet):
    """
    """
    """
    Override the defaults from DRF PG Builder.
    """
    filename = 'my_export.xlsx'

    def get_permission(self):
        return IsAuthenticated
```

### After the Files Are Built

After running the build command, you should have a directory created that you defined as `path` (or overrode with `get_root_python_path()`) that contains models, serializers, and a `urls.py` file. Include the `urls.py` file with a route from your Django project, and you should be able to visit the Django REST Framework browsable API.

## Known Issues

* Certain column types are not supported, such as `ts_vector` and others that don't map cleanly to a RESTful type.

## Release Notes and Contributors

* [Release notes](https://github.com/wharton/automagic-rest/releases)
* [Our wonderful contributors](https://github.com/wharton/automagic-rest/graphs/contributors)

## Maintainer

* [Timothy Allen](https://github.com/FlipperPA) at [The Wharton School](https://github.com/wharton)

This package is maintained by the staff of [Wharton Research Data Services](https://wrds.wharton.upenn.edu/). We are thrilled that [The Wharton School](https://www.wharton.upenn.edu/) allows us a certain amount of time to contribute to open-source projects. We add features as they are necessary for our projects, and try to keep up with Issues and Pull Requests as best we can. Due to constraints of time (our full time jobs!), Feature Requests without a Pull Request may not be implemented, but we are always open to new ideas and grateful for contributions and our package users.

