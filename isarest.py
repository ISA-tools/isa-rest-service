import os
import json
import io
import zipfile
from tempfile import TemporaryDirectory

from flask import Flask, Response, current_app, request, jsonify, send_file
from flask_restful import Api, Resource
from flask_restful_swagger import swagger
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
import config

from isatools.convert import isatab2json, isatab2sra, json2isatab, json2sra, sampletab2isatab, sampletab2json, \
    isatab2sampletab, json2sampletab, magetab2json
from isatools.net import mw2isa
from isatools.convert.isatab2cedar import ISATab2CEDAR
from isatools import isajson, isatab

from api.create import ISAStudyDesign
from api.archive import InvalidArchive, extract_validated_zip


SCIENTIFIC_DATA_EXTENSIONS = {
    '.bai', '.bam', '.cel', '.cram', '.csv', '.fastq', '.fq', '.gpr', '.gz',
    '.mzml', '.mzxml', '.nmrml', '.raw', '.sff', '.tsv', '.xml'
}
ISA_TAB_EXTENSIONS = {'.txt'} | SCIENTIFIC_DATA_EXTENSIONS
ISA_JSON_EXTENSIONS = {'.json'} | SCIENTIFIC_DATA_EXTENSIONS
MAGE_TAB_EXTENSIONS = {'.txt'} | SCIENTIFIC_DATA_EXTENSIONS


def _temporary_directory():
    if not os.path.isdir(config.UPLOAD_FOLDER):
        raise IOError("UPLOAD_FOLDER does not exist in file system or is not read/write-able")
    return TemporaryDirectory(dir=config.UPLOAD_FOLDER)


def _zip_directory(path):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for root, _, files in os.walk(path):
            for filename in files:
                file_path = os.path.join(root, filename)
                archive.write(file_path, os.path.relpath(file_path, path))
    payload.seek(0)
    return payload


def _write_request_data(request_, tmp_dir, file_name):
    file_path = os.path.join(tmp_dir, file_name)
    with open(file_path, 'wb') as output:
        output.write(request_.get_data())
    return file_path


def _extract_archive(file_path, destination, allowed_extensions):
    try:
        with zipfile.ZipFile(file_path, 'r') as archive:
            return extract_validated_zip(
                archive,
                destination,
                allowed_extensions=allowed_extensions,
                max_members=config.MAX_ARCHIVE_MEMBERS,
                max_member_size=config.MAX_ARCHIVE_MEMBER_SIZE,
                max_total_size=config.MAX_ARCHIVE_TOTAL_SIZE
            )
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise InvalidArchive("Request does not contain a valid ZIP archive") from error


def _extract_request_archive(request_, tmp_dir, allowed_extensions):
    file_path = _write_request_data(request_, tmp_dir, 'input.zip')
    extraction_dir = os.path.join(tmp_dir, 'extracted')
    os.mkdir(extraction_dir)
    extracted_files = _extract_archive(file_path, extraction_dir, allowed_extensions)
    return extraction_dir, extracted_files


def _error_response(status, message):
    response = jsonify(status=status, error={'message': message})
    response.status_code = status
    return response


def _conversion_error(message):
    current_app.logger.exception(message)
    return _error_response(500, "Conversion failed")


class ConvertTabToJson(Resource):

    """Convert to ISA- tab (zip) to ISA-JSON"""
    @swagger.operation(
        summary='Convert ISA tab to JSON',
        notes='Converts a ZIP file containing a collection of ISA tab files to ISA-JSON',
        parameters=[
            {
                "name": "body",
                "description": "Given a ZIP file containing valid ISA tab files, convert and return a valid ISA-JSON",
                "required": True,
                "allowMultiple": False,
                "dataType": "ISA tab (ZIP)",
                "supportedContentTypes": ['application/zip'],
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. The converted ISA content should be in the returned JSON."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def post(self):
        if request.mimetype != "application/zip":
            return _error_response(415, "Expected application/zip")
        try:
            with _temporary_directory() as tmp_dir:
                src_dir, _ = _extract_request_archive(request, tmp_dir, ISA_TAB_EXTENSIONS)
                result = isatab2json.convert(src_dir, validate_first=False, use_new_parser=True)
                if result is None:
                    raise IOError("Could not generate JSON from input ISA-Tab")
                return jsonify(result)
        except InvalidArchive as error:
            return _error_response(400, str(error))
        except Exception:
            return _conversion_error("Could not convert ISA-Tab to JSON")


class ConvertJsonToTab(Resource):

    """Convert to ISA-JSON to ISA tab (zip)"""
    @swagger.operation(
        summary='Convert JSON to ISA tab (zip)',
        notes='Converts an ISA-JSON file to ISA tab set of files as a zip file',
        parameters=[
            {
                "name": "body",
                "description": "Given a valid ISA-JSON, this function returns a zip file containing valid ISA tab files",
                "required": True,
                "allowMultiple": False,
                "dataType": "ISA JSON",
                "supportedContentTypes": ['application/json'],
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. The converted ISA content should be in the returned ZIP."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def post(self):
        if request.mimetype != "application/json":
            return _error_response(415, "Expected application/json")
        try:
            with _temporary_directory() as tmp_dir:
                file_path = _write_request_data(request, tmp_dir, 'input.json')
                with open(file_path) as fd:
                    json2isatab.convert(fd, tmp_dir)
                os.remove(file_path)
                return send_file(_zip_directory(tmp_dir), mimetype='application/zip')
        except Exception:
            return _conversion_error("Could not convert JSON to ISA-Tab")


class ConvertTabToSra(Resource):

    """Convert to ISA tab (zip) to SRA XML (zip)"""
    @swagger.operation(
        summary='Convert ISA tab to SRA',
        notes='Converts a ZIP file containing a collection of ISA-Tab files to ISA-JSON',
        parameters=[
            {
                "name": "body",
                "description": "Given a ZIP file containing valid ISA tab files, convert and return a valid set of SRA XML files (zip)",
                "required": True,
                "allowMultiple": False,
                "dataType": "ISA tab (ZIP)",
                "supportedContentTypes": ['application/zip'],
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. The converted SRA content should be in the returned ZIP."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def post(self):
        if request.mimetype != "application/zip":
            return _error_response(415, "Expected application/zip")
        try:
            with _temporary_directory() as tmp_dir, _temporary_directory() as target_tmp_dir:
                src_dir, _ = _extract_request_archive(request, tmp_dir, ISA_TAB_EXTENSIONS)
                isatab2sra.convert(src_dir, target_tmp_dir, validate_first=False)
                return send_file(_zip_directory(target_tmp_dir), mimetype='application/zip')
        except InvalidArchive as error:
            return _error_response(400, str(error))
        except Exception:
            return _conversion_error("Could not convert ISA-Tab to SRA")


class ConvertJsonToSra(Resource):

    """Convert to ISA tab (zip) to SRA XML (zip)"""
    @swagger.operation(
        summary='Convert ISA JSON to SRA',
        notes='Converts a ISA JSON file with data (ZIP) to SRA XML files (ZIP)',
        parameters=[
            {
                "name": "body",
                "description": "Given a ZIP file containing valid ISA tab files, convert and return a valid set of SRA XML files (zip)",
                "required": True,
                "allowMultiple": False,
                "dataType": "ISA tab (ZIP)",
                "supportedContentTypes": ['application/zip'],
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. The converted SRA content should be in the returned ZIP."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def post(self):
        if request.mimetype != "application/zip":
            return _error_response(415, "Expected application/zip")
        try:
            with _temporary_directory() as tmp_dir, _temporary_directory() as target_tmp_dir:
                _, extracted_files = _extract_request_archive(request, tmp_dir, ISA_JSON_EXTENSIONS)
                json_files = [path for path in extracted_files if path.lower().endswith('.json')]
                if len(json_files) != 1:
                    raise InvalidArchive("Archive must contain exactly one JSON file")
                with open(json_files[0]) as json_fp:
                    json2sra.convert(json_fp, target_tmp_dir, validate_first=False)
                return send_file(_zip_directory(target_tmp_dir), mimetype='application/zip')
        except InvalidArchive as error:
            return _error_response(400, str(error))
        except Exception:
            return _conversion_error("Could not convert ISA JSON to SRA")


class ConvertTabToCedar(Resource):

    """Convert to ISA tab (zip) to CEDAR JSON"""
    @swagger.operation(
        summary='Convert ISA tab to JSON',
        notes='Converts a ZIP file containing a collection of ISA tab files to CEDAR JSON',
        parameters=[
            {
                "name": "body",
                "description": "Given a ZIP file containing valid ISA tab files, convert and return a valid CEDAR JSON format (single file).",
                "required": True,
                "allowMultiple": False,
                "dataType": "ISA tab (ZIP)",
                "supportedContentTypes": ['application/zip'],
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. The converted ISA content should be in the returned JSON."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def post(self):
        if request.mimetype != "application/zip":
            return _error_response(415, "Expected application/zip")
        try:
            with _temporary_directory() as tmp_dir:
                src_dir, _ = _extract_request_archive(request, tmp_dir, ISA_TAB_EXTENSIONS)
                tab2cedar = ISATab2CEDAR('http://www.isa-tools.org/')
                tab2cedar.createCEDARjson(src_dir, src_dir, True)
                files = [name for name in os.listdir(src_dir) if name.endswith('.json')]
                if len(files) != 1:
                    raise IOError("Expected exactly one CEDAR JSON output")
                with open(os.path.join(src_dir, files[0])) as combined_json_file:
                    return jsonify(json.load(combined_json_file))
        except InvalidArchive as error:
            return _error_response(400, str(error))
        except Exception:
            return _conversion_error("Could not convert ISA-Tab to CEDAR JSON")


class ValidateIsaJSON(Resource):

    """Validate an ISA JSON document"""

    @swagger.operation(
        summary='Validate ISA JSON',
        notes='Validates a ZIP file containing a ISA JSON file and data files',
        parameters=[
            {
                "name": "body",
                "description": "Given a ZIP file containing an ISA JSON and data files, unpack and run the validator on the contents",
                "required": True,
                "allowMultiple": False,
                "dataType": "ISA tab (ZIP)",
                "supportedContentTypes": ['application/zip'],
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. A JSON validation report should be in the returned."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def post(self):
        if request.mimetype != "application/json":
            return _error_response(415, "Expected application/json")
        try:
            with _temporary_directory() as tmp_dir:
                file_path = _write_request_data(request, tmp_dir, 'input.json')
                with open(file_path) as input_file:
                    return jsonify(isajson.validate(input_file))
        except Exception:
            current_app.logger.exception("Could not validate ISA JSON")
            return _error_response(500, "Validation failed")


class ValidateIsaTab(Resource):

    """Validate an ISA tab document"""

    @swagger.operation(
        summary='Validate ISA tab',
        notes='Validates a ZIP file containing ISA tab files',
        parameters=[
            {
                "name": "body",
                "description": "Given a ZIP file containing an ISA tab, unpack and run the validator on the contents",
                "required": True,
                "allowMultiple": False,
                "dataType": "ISA tab (ZIP)",
                "supportedContentTypes": ['application/zip'],
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. A JSON validation report should be in the returned."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def post(self):
        if request.mimetype != "application/zip":
            return _error_response(415, "Expected application/zip")
        try:
            with _temporary_directory() as tmp_dir:
                _, extracted_files = _extract_request_archive(request, tmp_dir, ISA_TAB_EXTENSIONS)
                investigation_files = [
                    path for path in extracted_files
                    if os.path.basename(path).startswith('i_') and path.endswith('.txt')
                ]
                if len(investigation_files) != 1:
                    raise InvalidArchive("Archive must contain exactly one investigation file")
                with open(investigation_files[0]) as input_file:
                    return jsonify(isatab.validate(input_file))
        except InvalidArchive as error:
            return _error_response(400, str(error))
        except Exception:
            current_app.logger.exception("Could not validate ISA-Tab")
            return _error_response(500, "Validation failed")


class ImportMWToIsaTab(Resource):

    """Convert to ISA tab (zip) to SRA XML (zip)"""
    @swagger.operation(
        summary='Import from Metabolomics Workbench to ISA-Tab',
        notes='Imports a study from Metabolomics Workbench to ISA-Tab',
        parameters=[
            {
                "name": "studyid",
                "description": "Study ID",
                "type": "String",
                "required": True
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. The converted MW content should be in the returned ZIP."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def get(self, studyid):
        try:
            with _temporary_directory() as tmp_dir:
                mw2isa.mw2isa_convert(studyid=studyid, outputdir=tmp_dir, dl_option="no", validate_option="no")
                return send_file(_zip_directory(os.path.join(tmp_dir, studyid)), mimetype='application/zip')
        except Exception:
            return _conversion_error("Could not import Metabolomics Workbench study")


class ConvertSampleTabToIsaTab(Resource):

    """Convert SampleTab to ISA-Tab"""
    @swagger.operation(
        summary='Convert SampleTab to ISA-Tab',
        notes='Converts a SampleTab to a set of ISA-Tab files (ZIP)',
        parameters=[
            {
                "name": "body",
                "description": "Given a SampleTab file convert and return a valid set of ISA-Tab files (zip)",
                "required": True,
                "allowMultiple": False,
                "dataType": "SampleTab",
                "supportedContentTypes": ['text/tab-separated-values'],
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. The converted SampleTab content should be in the returned ZIP."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def post(self):
        if request.mimetype != "text/tab-separated-values":
            return _error_response(415, "Expected text/tab-separated-values")
        try:
            with _temporary_directory() as tmp_dir, _temporary_directory() as target_tmp_dir:
                file_path = _write_request_data(request, tmp_dir, 'input.txt')
                with open(file_path) as input_file:
                    sampletab2isatab.convert(input_file, target_tmp_dir)
                return send_file(_zip_directory(target_tmp_dir), mimetype='application/zip')
        except Exception:
            return _conversion_error("Could not convert SampleTab to ISA-Tab")


class ConvertSampleTabToJson(Resource):

    """Convert SampleTab to ISA-JSON"""
    @swagger.operation(
        summary='Convert SampleTab to ISA-JSON',
        notes='Converts a SampleTab to a set of ISA-JSON',
        parameters=[
            {
                "name": "body",
                "description": "Given a SampleTab file convert and return a valid ISA-JSON",
                "required": True,
                "allowMultiple": False,
                "dataType": "SampleTab",
                "supportedContentTypes": ['text/tab-separated-values'],
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. The converted SampleTab content should be in the returned ISA-JSON."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def post(self):
        if request.mimetype != "text/tab-separated-values":
            return _error_response(415, "Expected text/tab-separated-values")
        try:
            with _temporary_directory() as tmp_dir:
                file_path = _write_request_data(request, tmp_dir, 'input.txt')
                output_path = os.path.join(tmp_dir, 'output.json')
                with open(file_path) as input_file, open(output_path, 'w') as output_file:
                    sampletab2json.convert(input_file, output_file)
                with open(output_path) as output_file:
                    return jsonify(json.load(output_file))
        except Exception:
            return _conversion_error("Could not convert SampleTab to JSON")


class ConvertJsonToSampleTab(Resource):

    """Convert to ISA-JSON to SampleTab"""
    @swagger.operation(
        summary='Convert ISA-JSON to SampleTab',
        notes='Converts a ISA-JSON file to SampleTab',
        parameters=[
            {
                "name": "body",
                "description": "Given a valid ISA-JSON file, convert and return a SampleTab file",
                "required": True,
                "allowMultiple": False,
                "dataType": "ISA-JSON",
                "supportedContentTypes": ['application/json'],
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. The converted ISA-JSON content should be in the returned SampleTab."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def post(self):
        if request.mimetype != "application/json":
            return _error_response(415, "Expected application/json")
        try:
            with _temporary_directory() as tmp_dir:
                file_path = _write_request_data(request, tmp_dir, 'in.json')
                output_path = os.path.join(tmp_dir, 'out.txt')
                with open(file_path) as json_fp, open(output_path, 'w') as output_file:
                    json2sampletab.convert(json_fp, output_file)
                with open(output_path) as output_file:
                    return Response(output_file.read(), mimetype='text/tab-separated-values')
        except Exception:
            return _conversion_error("Could not convert ISA JSON to SampleTab")


class ConvertIsaTabToSampleTab(Resource):

    """Convert to ISA-JSON to SampleTab"""
    @swagger.operation(
        summary='Convert ISA-Tab to SampleTab',
        notes='Converts a ISA-Tab file to SampleTab',
        parameters=[
            {
                "name": "body",
                "description": "Given a valid ISA-Tab file, convert and return a SampleTab file",
                "required": True,
                "allowMultiple": False,
                "dataType": "ISA-Tab (ZIP)",
                "supportedContentTypes": ['application/zip'],
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. The converted ISA-Tab content should be in the returned SampleTab."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def post(self):
        if request.mimetype != "application/zip":
            return _error_response(415, "Expected application/zip")
        try:
            with _temporary_directory() as tmp_dir:
                _, extracted_files = _extract_request_archive(request, tmp_dir, ISA_TAB_EXTENSIONS)
                investigation_files = [
                    path for path in extracted_files
                    if os.path.basename(path).startswith('i_') and path.endswith('.txt')
                ]
                if len(investigation_files) != 1:
                    raise InvalidArchive("Archive must contain exactly one investigation file")
                output_path = os.path.join(tmp_dir, 'out.txt')
                with open(investigation_files[0]) as input_file, open(output_path, 'w') as output_file:
                    isatab2sampletab.convert(input_file, output_file)
                with open(output_path, 'rb') as output_file:
                    payload = io.BytesIO(output_file.read())
                return send_file(payload, mimetype='text/tab-separated-values')
        except InvalidArchive as error:
            return _error_response(400, str(error))
        except Exception:
            return _conversion_error("Could not convert ISA-Tab to SampleTab")


class ConvertMageTabToJson(Resource):

    """Convert MAGE-TAB (zip) to ISA-JSON"""
    @swagger.operation(
        summary='Convert MAGE-TAB to JSON',
        notes='Converts a ZIP file containing a collection of MAGE-TAB files to ISA-JSON',
        parameters=[
            {
                "name": "body",
                "description": "Given a ZIP file containing valid MAGE-TAB files, convert and return a valid ISA-JSON",
                "required": True,
                "allowMultiple": False,
                "dataType": "MAGE-TAB (ZIP)",
                "supportedContentTypes": ['application/zip'],
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. The converted MAGE-TAB content should be in the returned JSON."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def post(self):
        if request.mimetype != "application/zip":
            return _error_response(415, "Expected application/zip")
        try:
            with _temporary_directory() as tmp_dir:
                _, extracted_files = _extract_request_archive(request, tmp_dir, MAGE_TAB_EXTENSIONS)
                idf_files = [path for path in extracted_files if path.endswith('.idf.txt')]
                if len(idf_files) != 1:
                    raise InvalidArchive("Archive must contain exactly one IDF file")
                result = magetab2json.convert(idf_files[0])
                if result is None:
                    raise IOError("Could not generate JSON from input MAGE-TAB")
                return jsonify(result)
        except InvalidArchive as error:
            return _error_response(400, str(error))
        except Exception:
            return _conversion_error("Could not convert MAGE-TAB to JSON")


app = Flask(__name__)
app.config.from_object(config)
cors = CORS(app, resources={r"/api/*": {"origins": "*"}})


@app.errorhandler(RequestEntityTooLarge)
def handle_request_too_large(_error):
    return _error_response(413, "Request exceeds the permitted size")

api = swagger.docs(Api(app), apiVersion='0.8')
api.add_resource(ConvertTabToJson, '/api/v1/convert/tab-to-json')
api.add_resource(ConvertJsonToTab, '/api/v1/convert/json-to-tab')
api.add_resource(ConvertTabToSra, '/api/v1/convert/tab-to-sra')
api.add_resource(ConvertJsonToSra, '/api/v1/convert/json-to-sra')
api.add_resource(ConvertTabToCedar, '/api/v1/convert/tab-to-cedar')
api.add_resource(ValidateIsaJSON, '/api/v1/validate/json')
api.add_resource(ValidateIsaTab, '/api/v1/validate/isatab')
api.add_resource(ImportMWToIsaTab, '/api/v1/import/mw/<studyid>')
api.add_resource(ConvertSampleTabToIsaTab, '/api/v1/convert/sampletab-to-isatab')
api.add_resource(ConvertSampleTabToJson, '/api/v1/convert/sampletab-to-json')
api.add_resource(ConvertJsonToSampleTab, '/api/v1/convert/json-to-sampletab')
api.add_resource(ConvertIsaTabToSampleTab, '/api/v1/convert/isatab-to-sampletab')
api.add_resource(ConvertMageTabToJson, '/api/v1/convert/magetab-to-json')
api.add_resource(ISAStudyDesign, '/api/v1/isa-study-from-design')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=config.PORT, debug=config.DEBUG)
