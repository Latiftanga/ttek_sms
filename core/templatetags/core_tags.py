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
        'children': [
            {
                'label': 'All Students',
                'icon': 'fa-solid fa-users',
                'url_name': 'students:index',
            },
            {
                'label': 'Guardians',
                'icon': 'fa-solid fa-user-shield',
                'url_name': 'students:guardian_index',
            },
            {
                'label': 'Houses',
                'icon': 'fa-solid fa-flag',
                'url_name': 'students:houses',
            },
        ]
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
        'children': [
            {
                'label': 'Classes',
                'icon': 'fa-solid fa-chalkboard',
                'url_name': 'academics:classes',
            },
            {
                'label': 'Timetable',
                'icon': 'fa-solid fa-calendar-days',
                'url_name': 'academics:timetable',
            },
            {
                'label': 'Attendance',
                'icon': 'fa-solid fa-clipboard-check',
                'url_name': 'academics:attendance_reports',
            },
            {
                'label': 'Periods',
                'icon': 'fa-solid fa-clock',
                'url_name': 'academics:periods',
            },
            {
                'label': 'Classrooms',
                'icon': 'fa-solid fa-door-open',
                'url_name': 'academics:classrooms',
            },
        ]
    },
    {
        'label': 'Finance',
        'icon': 'fa-solid fa-coins',
        'url_name': 'finance:index',
        'roles': ['school_admin', 'superuser'],
        'children': [
            {
                'label': 'Fee Structures',
                'icon': 'fa-solid fa-layer-group',
                'url_name': 'finance:fee_structures',
            },
            {
                'label': 'Invoices',
                'icon': 'fa-solid fa-file-invoice',
                'url_name': 'finance:invoices',
            },
            {
                'label': 'Payments',
                'icon': 'fa-solid fa-money-bill-wave',
                'url_name': 'finance:payments',
            },
            {
                'label': 'Scholarships',
                'icon': 'fa-solid fa-graduation-cap',
                'url_name': 'finance:scholarships',
            },
            {
                'label': 'Reports',
                'icon': 'fa-solid fa-chart-bar',
                'url_name': 'finance:reports',
            },
        ]
    },
    {
        'label': 'Communications',
        'icon': 'fa-solid fa-comment-sms',
        'url_name': 'communications:index',
        'roles': ['school_admin', 'superuser'],
    },
    {
        'label': 'Gradebook',
        'icon': 'fa-solid fa-book-open',
        'url_name': 'gradebook:index',
        'roles': ['school_admin', 'superuser'],
        'children': [
            {
                'label': 'Score Entry',
                'icon': 'fa-solid fa-pen-to-square',
                'url_name': 'gradebook:score_entry',
            },
            {
                'label': 'Report Cards',
                'icon': 'fa-solid fa-file-lines',
                'url_name': 'gradebook:reports',
            },
            {
                'label': 'Settings',
                'icon': 'fa-solid fa-cog',
                'url_name': 'gradebook:settings',
            },
        ]
    },
    # Teacher navigation
    {
        'label': 'My Classes',
        'icon': 'fa-solid fa-chalkboard-user',
        'url_name': 'core:my_classes',
        'roles': ['teacher'],
    },
    {
        'label': 'Schedule',
        'icon': 'fa-solid fa-calendar-days',
        'url_name': 'core:schedule',
        'roles': ['teacher'],
    },
    {
        'label': 'Attendance',
        'icon': 'fa-solid fa-clipboard-user',
        'url_name': 'core:my_attendance',
        'roles': ['teacher'],
    },
    {
        'label': 'Grading',
        'icon': 'fa-solid fa-pen-to-square',
        'url_name': 'core:my_grading',
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


def is_url_active(request, url, url_name, exact=False):
    """Check if the current request path matches the nav item."""
    if url == '#':
        return False
    current_path = request.path
    # Exact match when either URL or current path is root
    if url == '/' or current_path == '/':
        return current_path == url
    # For exact matching (used by child items)
    if exact:
        return current_path == url or current_path.rstrip('/') == url.rstrip('/')
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
        current_path = request.path

        # First pass: check for startswith matches and find best match
        child_matches = []
        for child in item['children']:
            child_url = resolve_url(child['url_name'])
            if child_url != '#':
                url_base = child_url.rstrip('/')
                if current_path == child_url or current_path.rstrip('/') == url_base or current_path.startswith(url_base + '/'):
                    child_matches.append((child, child_url, len(child_url)))

        # Find the longest matching URL (most specific match)
        best_match_url = None
        if child_matches:
            best_match = max(child_matches, key=lambda x: x[2])
            best_match_url = best_match[1]

        # Second pass: build children list with correct active state
        for child in item['children']:
            child_url = resolve_url(child['url_name'])
            child_is_active = (child_url == best_match_url) if best_match_url else False
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
def floating_field(field, label=None, help_text=None, size='sm'):
    """
    Render a form field with DaisyUI floating label.

    Usage:
        {% floating_field form.name %}
        {% floating_field form.name "Custom Label" %}
        {% floating_field form.name label="Custom Label" help_text="Some help" %}
        {% floating_field form.name size="sm" %}
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

    # Size classes for DaisyUI components
    size_class = ''
    if size:
        size_map = {
            'xs': {'input': 'input-xs', 'select': 'select-xs', 'textarea': 'textarea-xs'},
            'sm': {'input': 'input-sm', 'select': 'select-sm', 'textarea': 'textarea-sm'},
            'lg': {'input': 'input-lg', 'select': 'select-lg', 'textarea': 'textarea-lg'},
        }
        if size in size_map:
            if 'select' in widget_type:
                size_class = size_map[size]['select']
            elif widget_type == 'textarea':
                size_class = size_map[size]['textarea']
            else:
                size_class = size_map[size]['input']

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
        'size': size,
        'size_class': size_class,
    }


@register.filter
def split(value, arg):
    """Split a string into a list."""
    return value.split(arg)


@register.filter
def get_item(dictionary, key):
    """
    Get an item from a dictionary by key.
    Usage: {{ my_dict|get_item:key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def multiply(value, arg):
    """
    Multiply value by arg.
    Usage: {{ value|multiply:arg }}
    """
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def get_category_score(grade, category):
    """
    Get the score for a specific category from SubjectTermGrade.category_scores.
    Usage: {{ grade|get_category_score:cat }}

    Args:
        grade: SubjectTermGrade object with category_scores JSONField
        category: AssessmentCategory object

    Returns:
        The score for that category, or None if not found
    """
    if grade is None or category is None:
        return None

    category_scores = getattr(grade, 'category_scores', None)
    if not category_scores:
        return None

    # Look up by category primary key (stored as string in JSON)
    cat_id = str(category.pk)
    cat_data = category_scores.get(cat_id)

    if cat_data and isinstance(cat_data, dict):
        score = cat_data.get('score')
        if score is not None:
            return round(score, 1)

    return None


# =============================================================================
# Form Input Template Tags
# =============================================================================

@register.inclusion_tag('core/partials/inputs/text_input.html')
def text_input(name, value='', label=None, placeholder='', required=False,
               disabled=False, readonly=False, help_text='', error='',
               input_class='', icon=None, size='sm'):
    """
    Render a text input field with DaisyUI styling.

    Usage:
        {% text_input "username" value=form_value label="Username" placeholder="Enter username" %}
        {% text_input "email" label="Email" icon="fa-solid fa-envelope" required=True %}
    """
    return {
        'name': name,
        'value': value,
        'label': label,
        'placeholder': placeholder,
        'required': required,
        'disabled': disabled,
        'readonly': readonly,
        'help_text': help_text,
        'error': error,
        'input_class': input_class,
        'icon': icon,
        'size': size,
        'input_type': 'text',
    }


@register.inclusion_tag('core/partials/inputs/text_input.html')
def email_input(name, value='', label=None, placeholder='', required=False,
                disabled=False, readonly=False, help_text='', error='',
                input_class='', icon='fa-solid fa-envelope', size='sm'):
    """Render an email input field."""
    return {
        'name': name,
        'value': value,
        'label': label,
        'placeholder': placeholder or 'Enter email address',
        'required': required,
        'disabled': disabled,
        'readonly': readonly,
        'help_text': help_text,
        'error': error,
        'input_class': input_class,
        'icon': icon,
        'size': size,
        'input_type': 'email',
    }


@register.inclusion_tag('core/partials/inputs/text_input.html')
def password_input(name, value='', label=None, placeholder='', required=False,
                   disabled=False, help_text='', error='', input_class='',
                   icon='fa-solid fa-lock', size='sm'):
    """Render a password input field."""
    return {
        'name': name,
        'value': value,
        'label': label,
        'placeholder': placeholder or 'Enter password',
        'required': required,
        'disabled': disabled,
        'readonly': False,
        'help_text': help_text,
        'error': error,
        'input_class': input_class,
        'icon': icon,
        'size': size,
        'input_type': 'password',
    }


@register.inclusion_tag('core/partials/inputs/text_input.html')
def number_input(name, value='', label=None, placeholder='', required=False,
                 disabled=False, readonly=False, help_text='', error='',
                 input_class='', icon=None, size='sm', min=None, max=None, step=None):
    """Render a number input field."""
    return {
        'name': name,
        'value': value,
        'label': label,
        'placeholder': placeholder,
        'required': required,
        'disabled': disabled,
        'readonly': readonly,
        'help_text': help_text,
        'error': error,
        'input_class': input_class,
        'icon': icon,
        'size': size,
        'input_type': 'number',
        'min': min,
        'max': max,
        'step': step,
    }


@register.inclusion_tag('core/partials/inputs/text_input.html')
def phone_input(name, value='', label=None, placeholder='', required=False,
                disabled=False, readonly=False, help_text='', error='',
                input_class='', icon='fa-solid fa-phone', size='sm'):
    """Render a phone input field."""
    return {
        'name': name,
        'value': value,
        'label': label,
        'placeholder': placeholder or 'Enter phone number',
        'required': required,
        'disabled': disabled,
        'readonly': readonly,
        'help_text': help_text,
        'error': error,
        'input_class': input_class,
        'icon': icon,
        'size': size,
        'input_type': 'tel',
    }


@register.inclusion_tag('core/partials/inputs/textarea_input.html')
def textarea_input(name, value='', label=None, placeholder='', required=False,
                   disabled=False, readonly=False, help_text='', error='',
                   input_class='', rows=4, size='sm'):
    """
    Render a textarea field with DaisyUI styling.

    Usage:
        {% textarea_input "description" label="Description" rows=5 %}
    """
    return {
        'name': name,
        'value': value,
        'label': label,
        'placeholder': placeholder,
        'required': required,
        'disabled': disabled,
        'readonly': readonly,
        'help_text': help_text,
        'error': error,
        'input_class': input_class,
        'rows': rows,
        'size': size,
    }


@register.inclusion_tag('core/partials/inputs/select_input.html')
def select_input(name, options, value='', label=None, required=False,
                 disabled=False, help_text='', error='', input_class='',
                 placeholder='Select an option', size='sm', icon=None):
    """
    Render a select dropdown with DaisyUI styling.

    Usage:
        {% select_input "status" options=status_choices value=current_status label="Status" %}

    Options should be a list of tuples: [(value, label), ...]
    Or a list of dicts: [{'value': 'x', 'label': 'X'}, ...]
    """
    # Normalize options to list of dicts
    normalized_options = []
    for opt in options:
        if isinstance(opt, (list, tuple)):
            normalized_options.append({'value': opt[0], 'label': opt[1]})
        elif isinstance(opt, dict):
            normalized_options.append(opt)
        else:
            normalized_options.append({'value': opt, 'label': str(opt)})

    return {
        'name': name,
        'options': normalized_options,
        'value': str(value) if value is not None else '',
        'label': label,
        'required': required,
        'disabled': disabled,
        'help_text': help_text,
        'error': error,
        'input_class': input_class,
        'placeholder': placeholder,
        'size': size,
        'icon': icon,
    }


@register.inclusion_tag('core/partials/inputs/date_input.html')
def date_input(name, value='', label=None, required=False, disabled=False,
               readonly=False, help_text='', error='', input_class='',
               min=None, max=None, size='sm'):
    """
    Render a date input field with DaisyUI styling.

    Usage:
        {% date_input "birth_date" label="Date of Birth" required=True %}
    """
    return {
        'name': name,
        'value': value,
        'label': label,
        'required': required,
        'disabled': disabled,
        'readonly': readonly,
        'help_text': help_text,
        'error': error,
        'input_class': input_class,
        'min': min,
        'max': max,
        'size': size,
        'input_type': 'date',
    }


@register.inclusion_tag('core/partials/inputs/date_input.html')
def time_input(name, value='', label=None, required=False, disabled=False,
               readonly=False, help_text='', error='', input_class='',
               min=None, max=None, size='sm'):
    """Render a time input field with DaisyUI styling."""
    return {
        'name': name,
        'value': value,
        'label': label,
        'required': required,
        'disabled': disabled,
        'readonly': readonly,
        'help_text': help_text,
        'error': error,
        'input_class': input_class,
        'min': min,
        'max': max,
        'size': size,
        'input_type': 'time',
    }


@register.inclusion_tag('core/partials/inputs/date_input.html')
def datetime_input(name, value='', label=None, required=False, disabled=False,
                   readonly=False, help_text='', error='', input_class='',
                   min=None, max=None, size='sm'):
    """Render a datetime input field with DaisyUI styling."""
    return {
        'name': name,
        'value': value,
        'label': label,
        'required': required,
        'disabled': disabled,
        'readonly': readonly,
        'help_text': help_text,
        'error': error,
        'input_class': input_class,
        'min': min,
        'max': max,
        'size': size,
        'input_type': 'datetime-local',
    }


@register.inclusion_tag('core/partials/inputs/file_input.html')
def file_input(name, label=None, required=False, disabled=False,
               help_text='', error='', input_class='', accept='',
               multiple=False, size='sm'):
    """
    Render a file input field with DaisyUI styling.

    Usage:
        {% file_input "photo" label="Profile Photo" accept="image/*" %}
        {% file_input "documents" label="Documents" multiple=True %}
    """
    return {
        'name': name,
        'label': label,
        'required': required,
        'disabled': disabled,
        'help_text': help_text,
        'error': error,
        'input_class': input_class,
        'accept': accept,
        'multiple': multiple,
        'size': size,
    }


@register.inclusion_tag('core/partials/inputs/checkbox_input.html')
def checkbox_input(name, checked=False, label=None, required=False,
                   disabled=False, help_text='', error='', input_class='',
                   value='true', size='sm', color='primary'):
    """
    Render a checkbox input with DaisyUI styling.

    Usage:
        {% checkbox_input "agree_terms" label="I agree to the terms" required=True %}
    """
    return {
        'name': name,
        'checked': checked,
        'label': label,
        'required': required,
        'disabled': disabled,
        'help_text': help_text,
        'error': error,
        'input_class': input_class,
        'value': value,
        'size': size,
        'color': color,
    }


@register.inclusion_tag('core/partials/inputs/toggle_input.html')
def toggle_input(name, checked=False, label=None, required=False,
                 disabled=False, help_text='', error='', input_class='',
                 value='true', size='sm', color='primary'):
    """
    Render a toggle switch with DaisyUI styling.

    Usage:
        {% toggle_input "is_active" label="Active" checked=True %}
    """
    return {
        'name': name,
        'checked': checked,
        'label': label,
        'required': required,
        'disabled': disabled,
        'help_text': help_text,
        'error': error,
        'input_class': input_class,
        'value': value,
        'size': size,
        'color': color,
    }


@register.inclusion_tag('core/partials/inputs/radio_group.html')
def radio_group(name, options, value='', label=None, required=False,
                disabled=False, help_text='', error='', inline=False,
                size='sm', color='primary'):
    """
    Render a group of radio buttons with DaisyUI styling.

    Usage:
        {% radio_group "gender" options=gender_choices value=selected label="Gender" %}
    """
    normalized_options = []
    for opt in options:
        if isinstance(opt, (list, tuple)):
            normalized_options.append({'value': opt[0], 'label': opt[1]})
        elif isinstance(opt, dict):
            normalized_options.append(opt)
        else:
            normalized_options.append({'value': opt, 'label': str(opt)})

    return {
        'name': name,
        'options': normalized_options,
        'value': str(value) if value is not None else '',
        'label': label,
        'required': required,
        'disabled': disabled,
        'help_text': help_text,
        'error': error,
        'inline': inline,
        'size': size,
        'color': color,
    }


@register.inclusion_tag('core/partials/inputs/search_input.html')
def search_input(name='search', value='', placeholder='Search...',
                 input_class='', size='sm', autofocus=False):
    """
    Render a search input with DaisyUI styling.

    Usage:
        {% search_input placeholder="Search students..." %}
    """
    return {
        'name': name,
        'value': value,
        'placeholder': placeholder,
        'input_class': input_class,
        'size': size,
        'autofocus': autofocus,
    }


# =============================================================================
# Form Field Wrapper (for Django form fields)
# =============================================================================

@register.inclusion_tag('core/partials/inputs/form_field.html')
def form_field(field, label=None, help_text=None, icon=None, size='sm'):
    """
    Render a Django form field with consistent DaisyUI styling.

    Usage:
        {% form_field form.username %}
        {% form_field form.email icon="fa-solid fa-envelope" %}
        {% form_field form.password label="Your Password" %}
    """
    widget_type = field.field.widget.__class__.__name__.lower()

    # Determine input type
    is_checkbox = widget_type == 'checkboxinput'
    is_select = 'select' in widget_type
    is_textarea = widget_type == 'textarea'
    is_file = 'file' in widget_type
    is_date = widget_type in ('dateinput', 'datetimeinput', 'timeinput')
    is_radio = widget_type == 'radioselect'

    # Get input type from widget attrs
    input_type = field.field.widget.attrs.get('type', 'text')
    if widget_type == 'dateinput':
        input_type = 'date'
    elif widget_type == 'timeinput':
        input_type = 'time'
    elif widget_type == 'datetimeinput':
        input_type = 'datetime-local'

    # Size classes
    size_classes = {
        'xs': 'input-xs',
        'sm': 'input-sm',
        'md': '',
        'lg': 'input-lg',
    }
    size_class = size_classes.get(size, '')

    return {
        'field': field,
        'label': label or field.label,
        'help_text': help_text or field.help_text,
        'icon': icon,
        'size': size,
        'size_class': size_class,
        'widget_type': widget_type,
        'input_type': input_type,
        'is_checkbox': is_checkbox,
        'is_select': is_select,
        'is_textarea': is_textarea,
        'is_file': is_file,
        'is_date': is_date,
        'is_radio': is_radio,
        'errors': field.errors,
        'required': field.field.required,
    }