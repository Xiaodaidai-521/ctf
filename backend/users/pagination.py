from rest_framework import serializers


def positive_query_integer(params, name, default):
    return serializers.IntegerField(min_value=1).run_validation(params.get(name, default))


def page_parameters(params, default_size=20):
    page = positive_query_integer(params, 'page', 1)
    page_size = min(100, positive_query_integer(params, 'page_size', default_size))
    return page, page_size
