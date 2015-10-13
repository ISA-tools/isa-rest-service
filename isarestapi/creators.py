import uuid
from flask import Response, request, jsonify
from flask_restful import Resource
from flask_restful_swagger import swagger
from isatools.io.isa_v1_model import Investigation

# keep objects in memory, no need to persist
investigations = []

class CreateInvestigation(Resource):

    def post(self):
        uid = str(uuid.uuid4())
        i = Investigation()
        investigations.append({uid: i})
        json = jsonify(uid=uid, rel='update', href='http://localhost:5000/isatools/update/investigation/' + uid)
        json.status_code = 201
        return json

    def get(self, uid):
        return '', 200

    def put(self, uid):
        return '', 200

    def delete(self, uid):
        return '', 204