import os

ENV = os.environ.get('ENVIRONMENT', 'dev')
# SECRET_KEY = os.environ.get('SECRET_KEY')

PROJECT_PATH = os.path.realpath(os.path.dirname(__file__))
ROOT_PATH = BASE_DIR = os.path.join(os.path.dirname(__file__), '..')

STATIC_FOLDER = os.path.join(ROOT_PATH, 'static')
TEMPLATE_FOLDER = os.path.join(ROOT_PATH, 'templates')
# CSRF_ENABLED = True

UPLOAD_FOLDER = os.path.join(ROOT_PATH, 'tests/tmp')
ALLOWED_EXTENSIONS = {'zip'}

if ENV == 'dev':
    PORT = 5000
    APP_BASE_LINK = 'http://localhost:' + str(PORT)
    DEBUG = True
else:
    APP_BASE_LINK = 'https://newt.oerc.ox.ac.uk'
    DEBUG = False
