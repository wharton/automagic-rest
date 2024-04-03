import keyword


def get_reserved_words():
    """
    A list of reserved words list that can not be used for Django field names. This
    includes the Python reserved words list, and additional fields not allowed by
    Django REST Framework.

    We will append `_var` to the model field names and map to the underlying database
    column in the models in the code generator.
    """
    reserved_words = keyword.kwlist
    reserved_words.append("format")

    return reserved_words
