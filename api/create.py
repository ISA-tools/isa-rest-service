from io import BytesIO
from zipfile import ZipFile
import json
import os
from tempfile import TemporaryDirectory

from flask import request, Flask, jsonify, send_file
from flask_restful import Resource
from flask_restful_swagger import swagger
from isatools.model import Investigation
from isatools.create.connectors import generate_study_design_from_config
from isatools import isatab
from isatools.isajson import ISAJSONEncoder

UNSUPPORTED_MIME_TYPE_ERROR = """
Unsupported mime type: {}. Only JSON accepted. See documentation for the correct JSON format you must provide.
"""

MISSING_PARAM_ERROR = """
Missing key in request JSON payload: {}. You need to provide both a valid 'studyDesignConfig' (see documentation) 
and a 'responseFormat' ('json', 'tab', 'all')
"""

OUTPUT_JSON_FILE_NAME = 'investigation.json'

CONTENT_TYPE_APPLICATION_ZIP = 'application/zip'
CONTENT_TYPE_APPLICATION_JSON = 'application/json'


class ISAStudyDesign(Resource):

    @swagger.operation(
        summary="Generate serialised Investigation out of study design config",
        notes="Generate serialised Investigation out of study design config",
        parameters=[
            {
                "name": "studyDesignConfig",
                "description": "the compact representation of a study Design, with arms, "
                               "elements (treatments and non-treatments) "
                               "and events (sampling and assay events)",
                "required": True,
                "allowedMultiple": False,
                "dataType": "JSON",
                "supportedContentTypes": ["application/json"],
                "paramType": "body"
            }, {
                "name": "responseFormat",
                "description": "either 'json', 'tab', 'json+tab'",
                "required": False,
                "allowedMultiple": False,
                "dataType": "string",
                "supportedContentTypes": ["application/json"],
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK."
            },
            {
                "code": 415,
                "message": UNSUPPORTED_MIME_TYPE_ERROR.format('text/html')
            }
        ]
    )
    def post(self):
        if not request.is_json:
            resp = jsonify(dict(
                status=415,
                message=UNSUPPORTED_MIME_TYPE_ERROR.format(request.mimetype)
            ))
            resp.status_code = 415
            return resp
        try:
            design_config = request.json['studyDesignConfig']
            res_format = request.json.get('responseFormat', 'tab')
            # TODO check if the studyDesignConfig is valid otherwise raise an error.
            study_design = generate_study_design_from_config(design_config)
            investigation = Investigation(studies=[study_design.generate_isa_study()])
            if res_format == 'json':
                return Flask.response_class(
                    status=200,
                    response=json.dumps(investigation, cls=ISAJSONEncoder),
                    mimetype=CONTENT_TYPE_APPLICATION_JSON
                )
            with TemporaryDirectory() as temp_dir:
                if res_format == 'all':
                    json_file_path = os.path.join(temp_dir, OUTPUT_JSON_FILE_NAME)
                    with open(json_file_path, 'w') as json_file:
                        json.dump(investigation, json_file, cls=ISAJSONEncoder)
                    isatab.dump(investigation, output_path=temp_dir)
                # in all the other cases we'll just provide the ISA-tab
                else:
                    isatab.dump(investigation, output_path=temp_dir)
                res_payload = BytesIO()
                with ZipFile(res_payload, 'w') as zip_file:
                    for file in os.listdir(temp_dir):
                        zip_file.write(os.path.join(temp_dir, file), file)
                res_payload.seek(0)
                return send_file(res_payload, mimetype=CONTENT_TYPE_APPLICATION_ZIP)
        except KeyError as ke:
            resp = jsonify(
                status=400,
                message=MISSING_PARAM_ERROR.format(ke.args[0])
            )
            resp.status_code = 400
            return resp


