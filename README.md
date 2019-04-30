# Automagic REST

Automagic REST automatically builds a full Django app as a Django REST Framework read-only environment for a set of tables in a PostgreSQL database.

This is very much in heavy development, being extracted from a production system and genericized for open source release.

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

`get_root_python_path` (default: `data_path`): a Python path where you would like to write the models, serializers, and routes. **IMPORTANT**: this path will be wiped and re-written every time the build command is run. It should be a dedicated directory with nothing else in it.

`get_view` (default: `automagic_rest.views.GenericViewSet`): the view to use.

`get_router` (default: `rest_framework.routers.DefaultRouter`): the router to use.

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
        owner the the schema owner user.
        """
        allowed_schemata = ['my_data', 'public_data']

        return allowed_schemata
```

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
from drf_renderer_xlsx.mixins import XLSXFileMixin

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

## Release Notes

### 0.2.0

* Refactored to use a generic serializer created on the fly. This is potentially a breaking change if you overrode the `get_serializer` method of the `build_data_models` command.
    * This has been replaced by a view method called `get_serializer_class_name`.
    * The serializer is now built on-the-fly rather than by the code generator.

### 0.1.2

* Add support for `DecimalField` with `max_digits` and `decimal_places` from `information_schema.columns` fields.

### 0.1.1

* Switched to naming models and serializers with a combination of `schema_name` and `table_name` to avoid model naming conflicts in Django if the same table exists across multiple schemata.

### 0.1.0

* Initial release.