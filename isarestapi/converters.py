import os
import uuid
import glob
import json
import shutil
from config import ALLOWED_EXTENSIONS, UPLOAD_FOLDER
from zipfile import ZipFile
from flask import Response, request, jsonify
from flask_restful import Resource
from flask_restful_swagger import swagger
from isatools.convert.isatab2json import IsatabToJsonWriter
from isatools.convert.json2isatab import JsonToIsatabWriter
from isatools.convert.isatab2cedar import ISATab2CEDAR


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS


def zipdir(path, ziph):
    # ziph is zipfile handle
    for root, dirs, files in os.walk(path):
        for file in files:
            ziph.write(os.path.join(root, file))


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
            json_data = request.get_data()
            converter = JsonToIsatabWriter()
            # write the json to somewhere input_file
            unique_id = str(uuid.uuid4())
            unique_filename = unique_id + ".json"
            ul_dir = UPLOAD_FOLDER
            json_file_path = os.path.join(ul_dir, unique_filename)
            # ensure this doesn't fail because of permissions on directory
            fd = os.open(json_file_path, os.O_CREAT | os.O_RDWR)
            os.write(fd, json_data)
            tab_dir = os.path.join(ul_dir, unique_id) # remove extension
            # again if this fails, it's probably a permissions problem
            os.mkdir(tab_dir)
            # Use converter to generate tab files
            converter.parsingJsonCombinedFile(json_file_path, tab_dir)
            # Zip and send back generated tab directory
            zipf = ZipFile(os.path.join(ul_dir, unique_id + '.zip'), 'w')
            zipdir(tab_dir, zipf)
            zipf.close()
            fd = open(os.path.join(ul_dir, unique_id + '.zip'), 'r')
            zipf_data = fd.read()
            zipf_data_length = len(zipf_data)
            fd.close()
            response.data = zipf_data
            response.headers.add('content-length', str(zipf_data_length))
            response.mimetype = "application/zip"
            response.status_code = 200
            return response
        else:
            return response


class ConvertIsaTabToJson(Resource):

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
            # Unzip the file and figure out if it's an XML archive or ISArchive
            # Get the data out of the request and write it to a temp file
            content = request.data
            unique_filename = str(uuid.uuid4())
            ul_dir = UPLOAD_FOLDER
            temp_dir = os.path.join(ul_dir, unique_filename)
            os.mkdir(temp_dir)
            f = open(os.path.join(temp_dir, unique_filename + '.zip'), 'w')
            f.write(content)
            f.close()
            zip_path = os.path.join(temp_dir, unique_filename + '.zip')
            with ZipFile(zip_path, 'r') as z:
                # extract ISArchive files
                z.extractall(temp_dir)
                writer = IsatabToJsonWriter()
                json_sub_dir = os.path.splitext(z.filename)[0] + "-json"
                json_dir = os.path.join(temp_dir, json_sub_dir)
                os.mkdir(json_dir)
                src_dir = os.path.normpath(os.path.join(temp_dir, z.filelist[0].filename))
                writer.parsingIsatab(src_dir, json_dir)
                # zip and build response of converted stuff
                # first clean up the junk expanded files
                for f in glob.glob(json_sub_dir + "/*_expanded.json"):
                    os.remove(f)
                # return just the combined JSON
                combined_json_file = os.path.join(json_dir, os.path.normpath(z.filelist[0].filename) + ".json")
                combined_json = json.load(open(combined_json_file))
                # cleanup generated directories
                shutil.rmtree(temp_dir, ignore_errors=True)
            response = jsonify(combined_json)
        return response

class ConvertIsaTabToCEDAR(Resource):

    """Convert to ISA-Tab archive to CEDAR-JSON"""
    @swagger.operation(
        notes='Converts an ISArchive ZIP file containing a collection of ISA-Tab files to CEDAR-JSON',
        parameters=[
            {
                "name": "body",
                "description": "Given a valid ISArchive ZIP file, convert and return a valid ISA-JSON (single file).",
                "required": True,
                "allowMultiple": False,
                "dataType": "ISArchive (ZIP)",
                "paramType": "body"
            }
        ],
        responseMessages=[
            {
                "code": 200,
                "message": "OK. The converted ISA content should be in the returned CEDAR-compliant JSON."
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
            # Unzip the file and figure out if it's an XML archive or ISArchive
            # Get the data out of the request and write it to a temp file
            content = request.data
            unique_filename = str(uuid.uuid4())
            ul_dir = UPLOAD_FOLDER
            temp_dir = os.path.join(ul_dir, unique_filename)
            os.mkdir(temp_dir)
            f = open(os.path.join(temp_dir, unique_filename + '.zip'), 'w')
            f.write(content)
            f.close()
            zip_path = os.path.join(temp_dir, unique_filename + '.zip')
            with ZipFile(zip_path, 'r') as z:
                # extract ISArchive files
                z.extractall(temp_dir)
                isa2cedar = ISATab2CEDAR()
                json_sub_dir = os.path.splitext(z.filename)[0] + "-json"
                json_dir = os.path.join(temp_dir, json_sub_dir)
                os.mkdir(json_dir)
                src_dir = os.path.normpath(os.path.join(temp_dir, z.filelist[0].filename))
                isa2cedar.createCEDARjson(src_dir, json_dir, True)  # Param 3 (using inv identifier or not,expose in API
                # return just the combined JSON
                combined_json_file = os.path.join(json_dir, os.path.normpath(z.filelist[0].filename) + ".json")
                combined_json = json.load(open(combined_json_file))
                # cleanup generated directories
                shutil.rmtree(temp_dir, ignore_errors=True)
            response = jsonify(combined_json)
        return response



class ConvertSraToIsaTab:
    # TODO: Implement SRA conversion to ISA-Tab
    pass