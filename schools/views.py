# schools/views.py
from django.http import HttpResponse

def public_home(request):
    return HttpResponse("""
        <h1>Welcome to SchoolOS</h1>
        <p>This is the Public Landing Page.</p>
        <p><a href="/admin/">Go to Admin Panel</a> to create schools.</p>
    """)