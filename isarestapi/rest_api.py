from flask import Flask
from flask_restful import Api
from flask_restful_swagger import swagger
from isarestapi.converters import ConvertJsonToIsaTab, ConvertIsaTabToSra
from isarestapi import config

app = Flask(__name__)
app.config.from_object(config)

api = swagger.docs(Api(app), apiVersion='0.1')
api.add_resource(ConvertJsonToIsaTab, '/convert/json-to-isatab')
# api.add_resource(ConvertIsaTabToJson, '/convert/isatab-to-json')
# api.add_resource(ConvertIsaTabToCEDAR, '/convert/isatab-to-cedar')
api.add_resource(ConvertIsaTabToSra, '/convert/isatab-to-sra')
