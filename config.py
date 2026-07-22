import os

ENV = os.environ.get('ENVIRONMENT', 'dev')
# SECRET_KEY = os.environ.get('SECRET_KEY')

PROJECT_PATH = os.path.realpath(os.path.dirname(__file__))

STATIC_FOLDER = os.path.join(PROJECT_PATH, 'static')
TEMPLATE_FOLDER = os.path.join(PROJECT_PATH, 'templates')
# CSRF_ENABLED = True

UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', '/tmp')

# Bounds applied before and while expanding user-supplied archives.
MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 32 * 1024 * 1024))
MAX_ARCHIVE_MEMBERS = int(os.environ.get('MAX_ARCHIVE_MEMBERS', 256))
MAX_ARCHIVE_MEMBER_SIZE = int(os.environ.get('MAX_ARCHIVE_MEMBER_SIZE', 64 * 1024 * 1024))
MAX_ARCHIVE_TOTAL_SIZE = int(os.environ.get('MAX_ARCHIVE_TOTAL_SIZE', 256 * 1024 * 1024))

if ENV == 'dev':
    PORT = 5000
    APP_BASE_LINK = 'http://localhost:' + str(PORT)
    DEBUG = True
elif ENV == 'test':
    PORT = 5000
    APP_BASE_LINK = 'http://localhost:' + str(PORT)
    DEBUG = False
else:
    PORT = 5000
    APP_BASE_LINK = 'http://localhost:' + str(PORT)
    DEBUG = False
