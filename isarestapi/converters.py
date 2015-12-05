import os
import uuid
import shutil
from .config import ALLOWED_EXTENSIONS, UPLOAD_FOLDER
from zipfile import ZipFile
from flask import Response, request
from flask_restful import Resource
from flask_restful_swagger import swagger
from isatools.convert.json2isatab import JsonToIsatabWriter


def _allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS


def _zipdir(path, ziph):
    # ziph is zipfile handle
    for file in os.listdir(path):
        ziph.write(os.path.join(path, file), file)


def _create_temp_dir():
    unique_id = str(uuid.uuid4())
    ul_dir = os.path.join(UPLOAD_FOLDER, unique_id)
    os.mkdir(ul_dir)
    if os.path.exists(ul_dir):
        return ul_dir


def _write_request_data(request, tmp_dir, file_name):
    data = request.get_data()
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


class ConvertJsonToIsaTab(Resource):
    """Convert ISA-JSON to ISA-Tab archive"""
    @swagger.operation(
        notes='Converts ISA-JSON to and ISArchive ZIP file containing a collection of ISA-Tab files',
        parameters=[
            {
                "name": "body",
                "description": "Given a valid ISA-JSON (single file), convert and return a valid ISArchive.",
                "required": True,
                "allowMultiple": False,
                "dataType": "JSON",
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. The converted ISA content should be in the returned ISArchive ZIP."
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
            # Create temporary directory
            tmp_dir = _create_temp_dir()
            if tmp_dir is None:
                return Response(500)
            # Write request data to file
            file_path = _write_request_data(request, tmp_dir, "isa.json")
            if file_path is None:
                return Response(500)

            # Convert
            converter = JsonToIsatabWriter()
            converter.parsingJsonCombinedFile(file_path, tmp_dir)

            # Zip and send back generated tab directory
            os.remove(file_path)  # Remove json file before zipping up directory
            tmp_file = tmp_dir + '.zip'
            zip_path = os.path.join(tmp_dir, tmp_file)
            zip_file = ZipFile(zip_path, 'w')
            _zipdir(tmp_dir, zip_file)
            zip_file.close()

            # Build and send response back
            response = _file_to_response(response, zip_path, "application/zip")
            response.status_code = 200
            shutil.rmtree(tmp_dir, ignore_errors=True)
            os.remove(tmp_file)
            return response
        else:
            return response


# class ConvertIsaTabToJson(Resource):
#
#     """Convert to ISA-Tab archive to ISA-JSON"""
#     @swagger.operation(
#         summary='Convert ISA-Tab to JSON',
#         notes='Converts an ISArchive ZIP file containing a collection of ISA-Tab files to ISA-JSON (single combined '
#               'output)',
#         parameters=[
#             {
#                 "name": "body",
#                 "description": "Given a valid ISArchive ZIP file, convert and return a valid ISA-JSON (single file).",
#                 "required": True,
#                 "allowMultiple": False,
#                 "dataType": "ISArchive (ZIP)",
#                 "supportedContentTypes": ['application/zip'],
#                 "paramType": "body"
#             }
#         ],
#         responseMessages=[
#             {
#                 "code": 200,
#                 "message": "OK. The converted ISA content should be in the returned JSON."
#             },
#             {
#                 "code": 415,
#                 "message": "Media not supported. Unexpected MIME type sent."
#             }
#         ]
#     )
#     def post(self):
#         response = Response(status=415)
#         if request.mimetype == "application/zip":
#             # Create temporary directory
#             tmp_dir = _create_temp_dir()
#             if tmp_dir is None:
#                 return Response(500)
#             # Write request data to file
#             file_path = _write_request_data(request, tmp_dir, "isatab.zip")
#             if file_path is None:
#                 return Response(500)
#
#             # Extract ISArchive files
#             with ZipFile(file_path, 'r') as z:
#                 z.extractall(tmp_dir)
#
#                 # Convert
#                 writer = IsatabToJsonWriter()
#                 json_sub_dir = os.path.splitext(z.filename)[0] + "-json"
#                 json_dir = os.path.join(tmp_dir, json_sub_dir)
#                 os.mkdir(json_dir)
#                 src_dir = os.path.normpath(os.path.join(tmp_dir, z.filelist[0].filename))
#                 writer.parsingIsatab(src_dir, json_dir)
#
#                 # first clean up the junk expanded files
#                 for f in glob.glob(json_sub_dir + "/*_expanded.json"):
#                     os.remove(f)
#                 # return just the combined JSON
#                 combined_json_file = os.path.join(json_dir, os.path.normpath(z.filelist[0].filename) + ".json")
#                 combined_json = json.load(open(combined_json_file))
#                 # cleanup generated directories
#                 shutil.rmtree(tmp_dir, ignore_errors=True)
#             response = jsonify(combined_json)
#         return response


# class ConvertIsaTabToCEDAR(Resource):
#     """Convert to ISA-Tab archive to CEDAR-JSON"""
#     @swagger.operation(
#         notes='Converts an ISArchive ZIP file containing a collection of ISA-Tab files to CEDAR-JSON (single combined '
#               'output)',
#         parameters=[
#             {
#                 "name": "body",
#                 "description": "Given a valid ISArchive ZIP file, convert and return a valid CEDAR-JSON (single file).",
#                 "required": True,
#                 "allowMultiple": False,
#                 "dataType": "ISArchive (ZIP)",
#                 "supportedContentTypes": ['application/zip'],
#                 "paramType": "body"
#             }
#         ],
#         responseMessages=[
#             {
#                 "code": 200,
#                 "message": "OK. The converted ISA content should be in the returned CEDAR-compliant JSON."
#             },
#             {
#                 "code": 415,
#                 "message": "Media not supported. Unexpected MIME type sent."
#             }
#         ]
#     )
#     def post(self):
#         response = Response(status=415)
#         if request.mimetype == "application/zip":
#             # Create temporary directory
#             tmp_dir = _create_temp_dir()
#             if tmp_dir is None:
#                 return Response(500)
#             # Write request data to file
#             file_path = _write_request_data(request, "isatab.zip")
#             if file_path is None:
#                 return Response(500)
#
#             with ZipFile(file_path, 'r') as z:
#                 # extract ISArchive files
#                 z.extractall(tmp_dir)
#                 isa2cedar = ISATab2CEDAR()
#                 json_sub_dir = os.path.splitext(z.filename)[0] + "-json"
#                 json_dir = os.path.join(tmp_dir, json_sub_dir)
#                 os.mkdir(json_dir)
#                 src_dir = os.path.normpath(os.path.join(tmp_dir, z.filelist[0].filename))
#                 isa2cedar.createCEDARjson(src_dir, json_dir, True)  # Param 3 (using inv identifier or not,expose in API
#                 # return just the combined JSON
#                 combined_json_file = os.path.join(json_dir, os.path.normpath(z.filelist[0].filename) + ".json")
#                 combined_json = json.load(open(combined_json_file))
#                 # cleanup generated directories
#                 shutil.rmtree(tmp_dir, ignore_errors=True)
#             response = jsonify(combined_json)
#         return response


class ConvertIsaTabToSra(Resource):
    """Convert to ISA-Tab archive to SRA"""
    @swagger.operation(
        notes='Converts an ISArchive ZIP file containing a collection of ISA-Tab files to SRA XML ZIP file',
        parameters=[
            {
                "name": "body",
                "description": "Given a valid ISArchive ZIP file, convert and return a ZIP containing valid SRA XML.",
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
                "message": "OK. The converted ISA content should be in the returned SRA XML."
            },
            {
                "code": 415,
                "message": "Media not supported. Unexpected MIME type sent."
            }
        ]
    )
    def post(self):
        response = Response(status=415)
        if request.mimetype == 'application/zip':
            # Create temporary directory
            tmp_dir = _create_temp_dir()
            if tmp_dir is None:
                return Response(500)

            # Write request data to file
            file_path = _write_request_data(request, tmp_dir, 'isatab.zip')
            if file_path is None:
                return Response(500)

            # Setup path to configuration
            config_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                      'configurations/isaconfig-default_v2015-07-02')

            with ZipFile(file_path, 'r') as z:
                # extract ISArchive files
                z.extractall(tmp_dir)
                src_dir = os.path.normpath(os.path.join(tmp_dir, z.filelist[0].filename))

                # convert to SRA writes to /sra
                from isatools.convert import isatab2sra
                isatab2sra.create_sra(src_dir, tmp_dir, config_dir)
                zip_path = os.path.join(os.path.join(tmp_dir, 'sra.zip'))
                zip_file = ZipFile(os.path.join(zip_path), 'w')
                _zipdir(tmp_dir + '/sra/' + z.filelist[0].filename, zip_file)
                zip_file.close()

                # Build and send response back
                response = _file_to_response(response, zip_path, 'application/zip')
                response.status_code = 200
                shutil.rmtree(tmp_dir, ignore_errors=True)
        return response
