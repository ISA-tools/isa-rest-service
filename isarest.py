import os
import uuid
import shutil
import json
import io
import zipfile
from flask import Flask, Response, request, jsonify, send_file
from flask_restful import Api, Resource
from flask_restful_swagger import swagger
import config
from isatools.convert import isatab2json, isatab2sra, json2isatab, json2sra
from isatools.convert.isatab2cedar import ISATab2CEDAR


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1] in config.ALLOWED_EXTENSIONS


def _zipdir(path, ziph):
    # ziph is zipfile handle
    for file in os.listdir(path):
        ziph.write(os.path.join(path, file), file)


def _create_temp_dir():
    unique_id = str(uuid.uuid4())
    if not os.path.exists(config.UPLOAD_FOLDER):
        raise IOError("UPLOAD_FOLDER does not exist in file system or is not read/write-able")
    ul_dir = os.path.join(config.UPLOAD_FOLDER, unique_id)
    os.mkdir(ul_dir)
    if os.path.exists(ul_dir):
        return ul_dir


def _write_request_data(request_, tmp_dir, file_name):
    data = request_.get_data()
    file_path = os.path.join(tmp_dir, file_name)
    fd = os.open(file_path, os.O_CREAT | os.O_RDWR)
    os.write(fd, data)
    if os.path.exists(file_path):
        return file_path


def _file_to_response(response, file_path, mimetype):
    fd = open(file_path, 'rb')
    response.set_data(fd.read())
    fd.close()
    response.headers.add('content-length', str(len(response.get_data())))
    response.mimetype = mimetype
    return response


class ConvertTabToJson(Resource):

    """Convert to ISA- tab (zip) to ISA-JSON"""
    @swagger.operation(
        summary='Convert ISA-Tab to JSON',
        notes='Converts a ZIP file containing a collection of ISA-Tab files to ISA-JSON (single combined '
              'output)',
        parameters=[
            {
                "name": "body",
                "description": "Given a ZIP file containing valid ISA tab files, convert and return a valid ISA-JSON (single file).",
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
        response = Response(status=415)
        if request.mimetype == "application/zip":
            try:
                # Write request data to file
                tmp_file = str(uuid.uuid4()) + ".zip"
                file_path = _write_request_data(request, config.UPLOAD_FOLDER, tmp_file)
                if file_path is None:
                    return Response(500)
                # Extract ISArchive files
                with zipfile.ZipFile(file_path, 'r') as z:
                    # Create temporary directory
                    tmp_dir = _create_temp_dir()
                    if tmp_dir is None:
                        return Response(500)
                    z.extractall(tmp_dir)
                    # Convert
                    src_dir = os.path.normpath(os.path.join(tmp_dir, z.filelist[0].filename))
                    isatab2json.convert(src_dir, src_dir)
                    # return just the combined JSON
                    files = [f for f in os.listdir(src_dir) if f.endswith('.json')]
                    if len(files) == 1:  # current assumption is that only one JSON should exist to know what to return
                        combined_json_file = os.path.join(src_dir, files[0])
                        combined_json = json.load(open(combined_json_file))
                    else:
                        raise IOError("More than one .json was output - cannot disambiguate what to return")
            except Exception:
                return Response(status=500)
            finally:
                # cleanup generated directories
                shutil.rmtree(tmp_dir, ignore_errors=True)
                os.remove(os.path.join(config.UPLOAD_FOLDER, tmp_file))
            response = jsonify(combined_json)
        return response


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
        response = Response(status=415)
        if request.mimetype == "application/json":
            tmp_file = str(uuid.uuid4()) + ".json"
            tmp_dir = _create_temp_dir()
            try:
                # Write request data to file
                file_path = _write_request_data(request, config.UPLOAD_FOLDER, tmp_file)
                if file_path is None:
                    return Response(500)
                json2isatab.convert(open(file_path), tmp_dir)
                memf = io.BytesIO()
                with zipfile.ZipFile(memf, 'w') as zf:
                    for file in os.listdir(tmp_dir):
                        zf.write(os.path.join(tmp_dir, file), file)
                memf.seek(0)
                response = send_file(memf, mimetype='application/zip')
            finally:
                # cleanup generated directories
                shutil.rmtree(tmp_dir, ignore_errors=True)
                os.remove(os.path.join(config.UPLOAD_FOLDER, tmp_file))
        return response


class ConvertTabToSra(Resource):

    def post(self):
        response = Response(status=500)
        # Create temporary directory
        tmp_dir = _create_temp_dir()
        try:
            if tmp_dir is None:
                raise IOError("Could not create temporary directory " + tmp_dir)
            if not request.mimetype == "application/zip":
                raise TypeError("Incorrect media type received. Got " + request.mimetype + ", expected application/zip")
            else:
                # Write request data to file
                file_path = _write_request_data(request, tmp_dir, 'isatab.zip')
                if file_path is None:
                    raise IOError("Could not create temporary file " + file_path)

                # Setup path to configuration
                config_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'isaconfig-default')

                with zipfile.ZipFile(file_path, 'r') as z:
                    # extract ISArchive files
                    z.extractall(tmp_dir)
                    src_dir = os.path.normpath(os.path.join(tmp_dir, z.filelist[0].filename))
                    # convert to SRA writes to /sra
                    isatab2sra.create_sra(src_dir, tmp_dir, config_dir)
                    memf = io.BytesIO()
                    with zipfile.ZipFile(memf, 'w') as zf:
                        for file in os.listdir(tmp_dir + '/sra/' + z.filelist[0].filename):
                            zf.write(os.path.join(tmp_dir + '/sra/' + z.filelist[0].filename, file), file)
                    memf.seek(0)
                    response = send_file(memf, mimetype='application/zip')
        except TypeError:
            response = Response(status=415)
        except Exception:
            response = Response(status=500)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return response


class ConvertJsonToSra(Resource):

    def post(self):
        response = Response(status=500)
        # Create temporary directory
        tmp_dir = _create_temp_dir()
        target_tmp_dir = _create_temp_dir()
        try:
            if tmp_dir is None:
                raise IOError("Could not create temporary directory " + tmp_dir)
            if not request.mimetype == "application/zip":
                raise TypeError("Incorrect media type received. Got " + request.mimetype +
                                ", expected application/zip")
            else:
                # Write request data to file
                file_path = _write_request_data(request, tmp_dir, 'isatab.zip')
                if file_path is None:
                    raise IOError("Could not create temporary file " + file_path)

                # Setup path to configuration
                config_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'isaconfig-default')
                with zipfile.ZipFile(file_path, 'r') as z:
                    # extract ISArchive files
                    z.extractall(tmp_dir)
                    src_file_path = os.path.normpath(os.path.join(tmp_dir, z.filelist[0].filename))
                    # find just the combined JSON
                    json2sra.convert(open(src_file_path), target_tmp_dir, config_dir)
                    memf = io.BytesIO()
                    with zipfile.ZipFile(memf, 'w') as zf:
                        sub_path = os.path.splitext(z.filelist[0].filename)[0]
                        for file in os.listdir(target_tmp_dir + '/sra/' + sub_path):
                            zf.write(os.path.join(target_tmp_dir + '/sra/' + sub_path, file), file)
                    memf.seek(0)
                    response = send_file(memf, mimetype='application/zip')
        except TypeError as t:
            response = Response(status=415)
        except Exception as e:
            response = Response(status=500)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            shutil.rmtree(target_tmp_dir, ignore_errors=True)
            return response


class ConvertTabToCedar(Resource):

    """Convert to ISA tab (zip) to CEDAR JSON"""
    def post(self):
        response = Response(status=415)
        if request.mimetype == "application/zip":
            try:
                # Write request data to file
                tmp_file = str(uuid.uuid4()) + ".zip"
                file_path = _write_request_data(request, config.UPLOAD_FOLDER, tmp_file)
                if file_path is None:
                    return Response(500)
                # Extract ISArchive files
                with zipfile.ZipFile(file_path, 'r') as z:
                    # Create temporary directory
                    tmp_dir = _create_temp_dir()
                    if tmp_dir is None:
                        return Response(500)
                    z.extractall(tmp_dir)
                    # Convert
                    src_dir = os.path.normpath(os.path.join(tmp_dir, z.filelist[0].filename))
                    tab2cedar = ISATab2CEDAR('http://www.isa-tools.org/')
                    tab2cedar.createCEDARjson(src_dir, src_dir, True)
                    # return just the combined JSON
                    files = [f for f in os.listdir(src_dir) if f.endswith('.json')]
                    if len(files) == 1:  # current assumption is that only one JSON should exist to know what to return
                        combined_json_file = os.path.join(src_dir, files[0])
                        combined_json = json.load(open(combined_json_file))
                    else:
                        raise IOError("More than one .json was output - cannot disambiguate what to return")
            except Exception:
                return Response(status=500)
            finally:
                # cleanup generated directories
                shutil.rmtree(tmp_dir, ignore_errors=True)
                os.remove(os.path.join(config.UPLOAD_FOLDER, tmp_file))
            response = jsonify(combined_json)
        return response

app = Flask(__name__)
app.config.from_object(config)

api = swagger.docs(Api(app), apiVersion='0.1')
api.add_resource(ConvertTabToJson, '/api/v1/convert/tab-to-json')
api.add_resource(ConvertJsonToTab, '/api/v1/convert/json-to-tab')
api.add_resource(ConvertTabToSra, '/api/v1/convert/tab-to-sra')
api.add_resource(ConvertJsonToSra, '/api/v1/convert/json-to-sra')
api.add_resource(ConvertTabToCedar, '/api/v1/convert/tab-to-cedar')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=config.PORT, debug=config.DEBUG)
