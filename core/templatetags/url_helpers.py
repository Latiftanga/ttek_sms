# core/templatetags/url_helpers.py
from django import template
from django.urls import reverse, NoReverseMatch
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def logout_url(context):
    """
    Generate the correct logout URL based on current context
    """
    request = context.get('request')
    if not request:
        return reverse('logout')

    try:
        # Base logout URL
        logout_url = reverse('logout')

        # Add school parameter for localhost
        if getattr(request, 'is_localhost', False) and hasattr(request, 'tenant') and request.tenant:
            logout_url += f"?school={request.tenant.id}"

        return logout_url
    except NoReverseMatch:
        return '/logout/'


@register.simple_tag(takes_context=True)
def login_url(context):
    """
    Generate the correct login URL based on current context
    """
    request = context.get('request')
    if not request:
        return reverse('login')

    try:
        # Base login URL
        login_url = reverse('login')

        # Add school parameter for localhost
        if getattr(request, 'is_localhost', False) and hasattr(request, 'tenant') and request.tenant:
            login_url += f"?school={request.tenant.id}"

        return login_url
    except NoReverseMatch:
        return '/login/'


@register.inclusion_tag('core/components/logout_button.html', takes_context=True)
def logout_button(context, css_classes="", button_text="Logout"):
    """
    Render a logout button with correct URL
    """
    request = context.get('request')

    # Get logout URL safely
    try:
        logout_url_value = logout_url(context)
    except:
        logout_url_value = '/logout/'

    return {
        'logout_url': logout_url_value,
        'css_classes': css_classes,
        'button_text': button_text,
        'request': request
    }
