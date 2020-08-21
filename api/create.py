from io import BytesIO
from zipfile import ZipFile
import json
import os
from tempfile import TemporaryDirectory
import traceback

from flask import request, Flask, jsonify, send_file
from flask_restful import Resource
from flask_restful_swagger import swagger
from isatools.model import Investigation
from isatools.create.connectors import generate_study_design_from_config
from isatools import isatab
from isatools.isajson import ISAJSONEncoder
from functools import reduce

from api.validation import MAX_SUBJECT_SIZE, MAX_ARMS, MAX_SAMPLE_SIZE, MAX_ASSAY_COMBINATIONS

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


def validate_design_config(config):
    """
    This function perform a crude sanity check on the parameters supplied in a study design config
    If the validation passes it returns None
    If it fails it returns a tuple or dictionary with a list of validation errors
    """
    res = {}
    arms = config['selectedArms']
    sample_plan = config['samplePlan']
    assay_plan = [
        assay_config for assay_config in config['assayConfigs'] if config['selectedAssayTypes'][assay_config['name']]
    ]
    if len(arms) > MAX_ARMS:
        res['arms'] = 'too many study arms. Current limit is {}, user provided {}'.format(MAX_ARMS, len(arms))
    if any(arm['size'] > MAX_SUBJECT_SIZE for arm in arms):
        res['size'] = 'at least one group size exceeds the limit of {} subjects'.format(MAX_SUBJECT_SIZE)
    max_subj_size = max(arm['size'] for arm in arms)
    if any(
            size * max_subj_size > MAX_SAMPLE_SIZE for sample_type in sample_plan
            for arm_name, sizes in sample_type['sampleTypeSizes'].items()
            for size in sizes if size is not None
    ):
        res['sampleSize'] = 'at least one sample plan exceeds the limit of maximum sample size'
    assay_messages = {}
    for assay_type in assay_plan:
        assay_combinations = 0
        for node in assay_type['workflow']:
            if '#replicates' in node:
                combinations = reduce(
                    lambda param, val: len(param["values"])*val,
                    [val for key, val in node.items() if key != '#replicates'],
                    1
                )
                assay_combinations = max(assay_combinations, combinations)
        if assay_combinations > MAX_ASSAY_COMBINATIONS:
            assay_messages[assay_type['name']] = 'assay exceeds maximum type of {} allowed combinations: {}'.format(
                MAX_ASSAY_COMBINATIONS, assay_combinations
            )
    if assay_messages:
        res['assayPlan'] = assay_messages
    return res if res else None


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
        except KeyError as ke:
            resp = jsonify(
                status=400,
                message=MISSING_PARAM_ERROR.format(ke.args[0]),
                error=ke
            )
            resp.status_code = 400
            return resp
        try:
            # TODO check if the studyDesignConfig is valid otherwise raise an error.
            validation_errors = validate_design_config(design_config)
            if validation_errors:
                return Flask.response_class(
                    status=400,
                    response=validation_errors,
                    mimetype=CONTENT_TYPE_APPLICATION_JSON
                )
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
        except Exception as e:
            print('Exception caught: {}'.format(e))
            print('Trace is: {}'.format(traceback.format_exc()))
            resp = jsonify(
                status=500,
                message='some nasty error occurred',
                error={
                    'type': e.__class__.__name__,
                    'message': [str(x) for x in e.args],
                    'trace': traceback.format_exc()
                }
            )
            resp.status_code = 500
            return resp


