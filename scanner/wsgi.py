"""
WSGI config for scanner project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import sys
from django.core.wsgi import get_wsgi_application
sys.path.append('/var/www/html')
sys.path.append('/var/www/html/scanner')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scanner.settings')

application = get_wsgi_application()
