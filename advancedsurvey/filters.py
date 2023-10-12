from django.template.defaulttags import register

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def add_str(arg1, arg2):
    return str(arg1) + str(arg2)