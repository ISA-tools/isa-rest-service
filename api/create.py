import json

from flask import request, Response, jsonify
from flask_restful import Resource
from flask_restful_swagger import swagger
from isatools.model import Investigation
from isatools.create.connectors import generate_study_design_from_config
from isatools import isatab
from isatools.isajson import ISAJSONEncoder



UNSUPPORTED_MIME_TYPE_ERROR = """
Unsupported mime type: {}. Only JSON accepted. See documentation for the correct JSON format you must provide.
"""


class ISACreate(Resource):

    @swagger.operation(
        summary="Generate serialised Investigation out of study design config"
    )
    def post(self):
        if not request.is_json:
            resp = jsonify(dict(
                status=415,
                message=UNSUPPORTED_MIME_TYPE_ERROR.format(request.mimetype)
            ))
            resp.status_code = 415
            return resp
        design_config = request.json
        try:
            study_design = generate_study_design_from_config(design_config)
            investigation = Investigation(studies=[study_design.generate_isa_study()])
            # TODO read the output type to understand whether the user wants ISA-tab or ISA-JSON
            return json.dumps(investigation, cls=ISAJSONEncoder)
        except Exception as e:
            return Response(status=500)


