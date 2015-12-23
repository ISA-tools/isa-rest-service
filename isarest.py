import os
import uuid
import shutil
import json
from flask import Flask, Response, request, jsonify
from flask_restful import Api, Resource
from flask_restful_swagger import swagger
from zipfile import ZipFile
import config
from isatools.convert import isatab2json


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
    fd = open(os.path.join(file_path), 'r')
    response.data = fd.read()
    fd.close()
    response.headers.add('content-length', str(len(response.data)))
    response.mimetype = mimetype
    return response


class ConvertTabToJson(Resource):

    """Convert to ISA-Tab archive to ISA-JSON"""
    @swagger.operation(
        summary='Convert ISA-Tab to JSON',
        notes='Converts an ISArchive ZIP file containing a collection of ISA-Tab files to ISA-JSON (single combined '
              'output)',
        parameters=[
            {
                "name": "body",
                "description": "Given a valid ISArchive ZIP file, convert and return a valid ISA-JSON (single file).",
                "required": True,
                "allowMultiple": False,
                "dataType": "ISArchive (ZIP)",
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
                with ZipFile(file_path, 'r') as z:
                    # Create temporary directory
                    tmp_dir = _create_temp_dir()
                    if tmp_dir is None:
                        return Response(500)
                    z.extractall(tmp_dir)
                    # Convert
                    src_dir = os.path.normpath(os.path.join(tmp_dir, z.filelist[0].filename))
                    isatab2json.convert(src_dir, src_dir)
                    # return just the combined JSON
                    combined_json_file = os.path.join(src_dir, os.path.normpath(z.filelist[0].filename) + ".json")
                    combined_json = json.load(open(combined_json_file))
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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=config.PORT, debug=config.DEBUG)
