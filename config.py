import os

ENV = os.environ.get('ENVIRONMENT', 'dev')
# SECRET_KEY = os.environ.get('SECRET_KEY')

PROJECT_PATH = os.path.realpath(os.path.dirname(__file__))

STATIC_FOLDER = os.path.join(PROJECT_PATH, 'static')
TEMPLATE_FOLDER = os.path.join(PROJECT_PATH, 'templates')
# CSRF_ENABLED = True

UPLOAD_FOLDER = os.path.join(PROJECT_PATH, '/tmp')  # PUT THIS SOMEWHERE SENSIBLE
ALLOWED_EXTENSIONS = {'zip'}

if ENV == 'dev':
    PORT = 5000
    APP_BASE_LINK = 'http://localhost:' + str(PORT)
    DEBUG = True
else:
    APP_BASE_LINK = 'https://something.ox.ac.uk'
    DEBUG = False
