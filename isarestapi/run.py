from flask import Flask
from flask_restful import Api
from flask_restful_swagger import swagger
from converters import ConvertIsaTabToJson, ConvertJsonToIsaTab, ConvertSraToIsaTab

app = Flask(__name__)
api = swagger.docs(Api(app), apiVersion='0.1')
api.add_resource(ConvertJsonToIsaTab, '/convert/json-to-isatab')
api.add_resource(ConvertIsaTabToJson, '/convert/isatab-to-json')
#api.add_resource(ConvertSraToIsaTab, '/convert/sra-to-isatab')

if __name__ == '__main__':
    app.run(debug=True)
