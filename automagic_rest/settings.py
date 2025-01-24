import keyword

from django.conf import settings


def get_reserved_words_to_append_suffix():
    """
    A list of reserved words list that can not be used for Django field names. This
    includes the Python reserved words list, and additional fields not allowed by
    Django REST Framework.

    We will append the value returned by `get_reserved_word_suffix` to the model field
    names and map to the underlying database column in the models in the code generator.
    """
    reserved_words = keyword.kwlist
    reserved_words.append("format")

    return reserved_words


def get_reserved_word_suffix():
    """
    Returns the Django setting for the reserved word suffix, or the default of `var`.
    """

    return getattr(settings, "AUTOMAGIC_REST_RESERVED_WORD_SUFFIX", "var")
