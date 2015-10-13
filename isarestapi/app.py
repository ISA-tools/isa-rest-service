from flask import Flask
from flask_restful import Api
from converters import ConvertIsaTabToJson, ConvertJsonToIsaTab, ConvertSraToIsaTab

app = Flask(__name__)
app.config['ALLOWED_EXTENSIONS'] = {'zip'}
app.config['UPLOAD_FOLDER'] = '/Users/dj/PycharmProjects/isa-rest-api/tests/tmp'
api = Api(app)
api.add_resource(ConvertJsonToIsaTab, '/convert/json-to-isatab')
api.add_resource(ConvertIsaTabToJson, '/convert/isatab-to-json')
api.add_resource(ConvertSraToIsaTab, '/convert/sra-to-isatab')

if __name__ == '__main__':
    app.run(debug=True)
