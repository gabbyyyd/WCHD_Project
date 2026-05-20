from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key, "")

@register.filter
def get_attr(obj, attr):
    display_method_name = f"get_{attr}_display"

    if hasattr(obj, display_method_name):
        display_method = getattr(obj, display_method_name)
        return display_method()

    return getattr(obj, attr, "")

@register.filter
def money(value):
    if value is None or value == "":
        return ""
    return f"${float(value):,.2f}"