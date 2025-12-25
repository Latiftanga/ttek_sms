from django import template
from django.urls import reverse, NoReverseMatch

register = template.Library()


# Navigation config with role-based access
# roles: 'all', 'school_admin', 'teacher', 'student', 'parent', 'superuser'
NAVIGATION_CONFIG = [
    {
        'label': 'Dashboard',
        'icon': 'fa-solid fa-gauge',
        'url_name': 'core:index',
        'roles': ['all'],
    },
    # School Admin / Superuser navigation
    {
        'label': 'Students',
        'icon': 'fa-solid fa-user-graduate',
        'url_name': 'students:index',
        'roles': ['school_admin', 'superuser'],
    },
    {
        'label': 'Teachers',
        'icon': 'fa-solid fa-chalkboard-user',
        'url_name': 'teachers:index',
        'roles': ['school_admin', 'superuser'],
    },
    {
        'label': 'Academics',
        'icon': 'fa-solid fa-graduation-cap',
        'url_name': 'academics:index',
        'roles': ['school_admin', 'superuser'],
    },
    {
        'label': 'Finance',
        'icon': 'fa-solid fa-money-bill',
        'url_name': 'core:finance',
        'roles': ['school_admin', 'superuser'],
        'children': [
            {
                'label': 'Invoices',
                'icon': 'fa-solid fa-file-invoice',
                'url_name': 'core:invoices',
            },
            {
                'label': 'Payments',
                'icon': 'fa-solid fa-credit-card',
                'url_name': 'core:payments',
            },
        ]
    },
    {
        'label': 'Communications',
        'icon': 'fa-solid fa-envelope',
        'url_name': 'core:communications',
        'roles': ['school_admin', 'superuser'],
    },
    # Teacher navigation
    {
        'label': 'My Classes',
        'icon': 'fa-solid fa-chalkboard',
        'url_name': 'core:my_classes',
        'roles': ['teacher'],
    },
    {
        'label': 'Attendance',
        'icon': 'fa-solid fa-clipboard-user',
        'url_name': 'core:attendance',
        'roles': ['teacher'],
    },
    {
        'label': 'Grading',
        'icon': 'fa-solid fa-pen-to-square',
        'url_name': 'core:grading',
        'roles': ['teacher'],
    },
    # Student navigation
    {
        'label': 'My Results',
        'icon': 'fa-solid fa-chart-line',
        'url_name': 'core:my_results',
        'roles': ['student'],
    },
    {
        'label': 'Timetable',
        'icon': 'fa-solid fa-calendar-days',
        'url_name': 'core:timetable',
        'roles': ['student'],
    },
    {
        'label': 'My Fees',
        'icon': 'fa-solid fa-receipt',
        'url_name': 'core:my_fees',
        'roles': ['student'],
    },
    # Parent navigation
    {
        'label': 'My Wards',
        'icon': 'fa-solid fa-children',
        'url_name': 'core:my_wards',
        'roles': ['parent'],
    },
    {
        'label': 'Fee Payments',
        'icon': 'fa-solid fa-credit-card',
        'url_name': 'core:fee_payments',
        'roles': ['parent'],
    },
]


def get_user_roles(user):
    """Get list of roles for the current user."""
    if not user or not user.is_authenticated:
        return []

    roles = []
    if user.is_superuser:
        roles.append('superuser')
    if getattr(user, 'is_school_admin', False):
        roles.append('school_admin')
    if getattr(user, 'is_teacher', False):
        roles.append('teacher')
    if getattr(user, 'is_student', False):
        roles.append('student')
    if getattr(user, 'is_parent', False):
        roles.append('parent')

    return roles


def user_has_access(user_roles, item_roles):
    """Check if user has access to a navigation item."""
    if 'all' in item_roles:
        return True
    return any(role in item_roles for role in user_roles)


def resolve_url(url_name):
    """Safely resolve URL name to URL path."""
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return '#'


def is_url_active(request, url, url_name):
    """Check if the current request path matches the nav item."""
    if url == '#':
        return False
    current_path = request.path
    # Exact match when either URL or current path is root
    if url == '/' or current_path == '/':
        return current_path == url
    return current_path == url or current_path.startswith(url.rstrip('/') + '/')


def process_nav_item(item, request):
    """Process a navigation item and its children."""
    url = resolve_url(item['url_name'])
    is_active = is_url_active(request, url, item['url_name'])

    processed = {
        'label': item['label'],
        'icon': item['icon'],
        'url': url,
        'is_active': is_active,
    }

    if 'children' in item:
        children = []
        for child in item['children']:
            child_url = resolve_url(child['url_name'])
            child_is_active = is_url_active(request, child_url, child['url_name'])
            children.append({
                'label': child['label'],
                'icon': child['icon'],
                'url': child_url,
                'is_active': child_is_active,
            })
            if child_is_active:
                processed['is_active'] = True
        processed['children'] = children

    return processed


@register.simple_tag(takes_context=True)
def get_navigation_items(context):
    """
    Returns the navigation items for the sidebar based on user role.
    Marks the current page as active based on the request path.
    """
    request = context.get('request')
    if not request:
        return []

    user = getattr(request, 'user', None)
    user_roles = get_user_roles(user)

    nav_items = []
    for item in NAVIGATION_CONFIG:
        item_roles = item.get('roles', ['all'])
        if user_has_access(user_roles, item_roles):
            nav_items.append(process_nav_item(item, request))

    return nav_items


@register.simple_tag(takes_context=True)
def nav_is_active(context, url_name):
    """
    Check if a URL name matches the current page.
    Usage: {% nav_is_active 'core:index' as is_active %}
    """
    request = context.get('request')
    if not request:
        return False

    url = resolve_url(url_name)
    return is_url_active(request, url, url_name)


@register.inclusion_tag('core/partials/stat_card.html')
def stat_card(title, value, icon, color='primary'):
    """
    Render a stat card component.
    Usage: {% stat_card "Students" "1,200" "fa-solid fa-users" "primary" %}
    """
    return {
        'title': title,
        'value': value,
        'icon': icon,
        'color': color,
    }


@register.simple_tag(takes_context=True)
def user_is_role(context, role):
    """
    Check if the current user has a specific role.
    Usage: {% user_is_role 'teacher' as is_teacher %}
    """
    request = context.get('request')
    if not request:
        return False

    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return False

    role_map = {
        'superuser': user.is_superuser,
        'school_admin': getattr(user, 'is_school_admin', False),
        'teacher': getattr(user, 'is_teacher', False),
        'student': getattr(user, 'is_student', False),
        'parent': getattr(user, 'is_parent', False),
    }
    return role_map.get(role, False)


@register.inclusion_tag('core/partials/floating_field.html')
def floating_field(field, label=None, help_text=None):
    """
    Render a form field with DaisyUI floating label.

    Usage:
        {% floating_field form.name %}
        {% floating_field form.name "Custom Label" %}
        {% floating_field form.name label="Custom Label" help_text="Some help" %}
    """
    # Determine field type for appropriate input class
    widget_type = field.field.widget.__class__.__name__.lower()

    # Map widget types to DaisyUI v5 classes (no -bordered suffix)
    input_class_map = {
        'textarea': 'textarea w-full',
        'select': 'select w-full',
        'fileinput': 'file-input w-full',
        'clearablefileinput': 'file-input w-full',
        'checkboxinput': 'checkbox',
        'numberinput': 'input w-full',
        'emailinput': 'input w-full',
        'passwordinput': 'input w-full',
        'urlinput': 'input w-full',
        'dateinput': 'input w-full',
        'datetimeinput': 'input w-full',
        'timeinput': 'input w-full',
    }

    input_class = input_class_map.get(widget_type, 'input w-full')

    # Check special input types
    widget_attrs = field.field.widget.attrs
    input_type = widget_attrs.get('type', 'text')

    if input_type == 'color':
        input_class = 'input p-1 h-12 w-full cursor-pointer'

    # Date/time inputs use wrapper class pattern in DaisyUI v5
    # Check both widget type and input type attr for robustness
    is_date_type = (
        widget_type in ('dateinput', 'datetimeinput', 'timeinput') or
        input_type in ('date', 'datetime-local', 'time')
    )

    # Ensure input_type is correct for date widgets
    if widget_type == 'dateinput':
        input_type = 'date'
    elif widget_type == 'datetimeinput':
        input_type = 'datetime-local'
    elif widget_type == 'timeinput':
        input_type = 'time'

    # Use custom label or field label
    field_label = label if label else field.label

    # Use custom help text or field help text
    field_help = help_text if help_text else field.help_text

    return {
        'field': field,
        'label': field_label,
        'help_text': field_help,
        'input_class': input_class,
        'input_type': input_type,
        'widget_type': widget_type,
        'is_checkbox': widget_type == 'checkboxinput',
        'is_textarea': widget_type == 'textarea',
        'is_select': 'select' in widget_type,
        'is_file': 'file' in widget_type,
        'is_date': is_date_type,
    }


@register.filter
def split(value, arg):
    """Split a string into a list."""
    return value.split(arg)