from django import template

register = template.Library()


@register.filter
def decimal_size(value):
    size = int(value)
    if size >= 1_000_000_000:
        return f"{size / 1_000_000_000:.1f} GB"
    if size >= 1_000_000:
        return f"{size / 1_000_000:.1f} MB"
    return f"{size:,} بایت"
