from flask_restx import Api, Namespace


API_PREFIX = '/api/v1'
SWAGGER_UI_PATH = '/docs'
SWAGGER_SPEC_PATH = '/swagger.json'

conversion_namespace = Namespace(
    'convert', description='ISA format conversion operations', path='/convert'
)
validation_namespace = Namespace(
    'validate', description='ISA validation operations', path='/validate'
)
import_namespace = Namespace(
    'import', description='External ISA import operations', path='/import'
)
study_namespace = Namespace(
    'study-design', description='ISA study-design generation', path='/'
)


def document_operation(
        namespace, *, summary, notes=None, parameters=None,
        responseMessages=None
):
    """Translate the former operation metadata into Flask-RESTX docs."""
    params = {}
    consumes = set()
    for parameter in parameters or ():
        content_types = parameter.get('supportedContentTypes', ())
        consumes.update(content_types)
        data_type = parameter.get('dataType', 'string')
        params[parameter['name']] = {
            'description': parameter.get('description', ''),
            'in': parameter.get('paramType', 'body'),
            'required': parameter.get('required', False),
            'schema': {
                'type': 'object' if data_type == 'JSON' else 'string'
            }
        }

    responses = {
        message['code']: message['message']
        for message in responseMessages or ()
    }
    options = {
        'summary': summary,
        'description': notes or summary,
        'params': params,
        'responses': responses
    }
    if consumes:
        options['consumes'] = sorted(consumes)
    return namespace.doc(**options)


def build_api(app):
    api = Api(
        app,
        version='1.0.0',
        title='ISA REST Service',
        description='Convert, validate, import, and generate ISA metadata.',
        prefix=API_PREFIX,
        doc=SWAGGER_UI_PATH,
        default_swagger_filename=SWAGGER_SPEC_PATH.lstrip('/'),
        ordered=True
    )
    api.add_namespace(conversion_namespace)
    api.add_namespace(validation_namespace)
    api.add_namespace(import_namespace)
    api.add_namespace(study_namespace)
    return api
