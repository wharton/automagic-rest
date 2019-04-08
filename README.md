# Automagic REST

Automagic REST automatically builds a full Django app as a Django REST Framework read-only environment for a set of tables in a PostgreSQL database.

This is very much in heavy development, being extracted from a production system and genericized for open source release.

## Installation

To get started, `pip install automagic-rest` and add `automagic_rest` to your `INSTALLED_APPS` setting in Django.

## Configuration and Customization

By default, Automagic REST will create a directory called `data_path` at the root of your Django project, where `manage.py` lives. The follow options can be passed to the command:

* `--database` (default: `my_pg_data`): the name of the Django database as defined in the `DATABASES` setting.
* `--owner` (default: `my_pg_user`): the name of the PostgreSQL user which owns the schemata. This will normally be the same as the `USER` in the `DATABASES` setting for the database above.
* `--path` (default: `data_path`): the path to write the models and serializers to. This path will be completely deleted and rewritten whenever the command is run, so be careful!

Example: `python manage.py build_data_models --database=my_data --owner=my_user --path=my_data_path`

Methods are provided which can be overridden to customize the endpoint with your own Django management command.

### class automagic_rest.management.commands.build_data_models.Command

`get_db` (default: `my_pg_data`): the name of the PostgreSQL database in Django's settings that we will introspect to build the API.

`get_owner` (default: `my_pg_user`): the name of the PostgreSQL user that owns the schemata we will introspect.

`get_allowed_schemata` (default: `None`): if set, returns a list of schemata in the database to be built. If `None`, selects all schemata for the specific user.

`get_root_python_path` (default: `data_path`): a Python path where you would like to write the models, serializers, and routes. **IMPORTANT**: this path will be wiped and re-written every time the build command is run. It should be a dedicated directory with nothing else in it.

`get_serializer` (default: `rest_framework.serializers.ModelSerializer`): the serializer to use.

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
        Get the list of products from SQL Server
        """
        allowed_schemata = ['my_data', 'public_data']

        return allowed_schemata
```
