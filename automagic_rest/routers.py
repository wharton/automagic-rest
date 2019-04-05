from collections import OrderedDict

from django.urls import NoReverseMatch

from pg_permissions import get_user_permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.routers import DefaultRouter


class PermittedAPIRootView(APIView):
    """
    These are the permitted endpoint routes.
    """

    _ignore_model_permissions = True
    exclude_from_schema = True
    api_root_dict = None

    def get(self, request, *args, **kwargs):
        # Return a plain {"name": "hyperlink"} response.
        ret = OrderedDict()
        namespace = request.resolver_match.namespace

        # Get the permitted products from PostgreSQL for the user
        permitted = get_user_permissions(request.user.username)

        for key, url_name in self.api_root_dict.items():
            # Check to see if the product is permitted for the user
            if key.split(".")[0] in permitted:
                if namespace:
                    url_name = namespace + ":" + url_name
                try:
                    ret[key] = reverse(
                        url_name,
                        args=args,
                        kwargs=kwargs,
                        request=request,
                        format=kwargs.get("format", None),
                    )
                except NoReverseMatch:
                    # Don't bail out if eg. no list routes exist, only detail routes.
                    continue

        return Response(ret)


class PermittedRouter(DefaultRouter):
    """
    Check permissions in PostgreSQL and return the dict.
    """

    APIRootView = PermittedAPIRootView
