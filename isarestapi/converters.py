import os
import uuid
import glob
import json
import shutil
from . import app
from zipfile import ZipFile
from werkzeug.utils import secure_filename
from flask import Response, request, jsonify
from flask_restful import Resource
from isatools.convert.isatab_to_json import IsatabToJsonWriter
from isatools.convert.json_to_isatab import JsonToIsatabWriter


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in app.config['ALLOWED_EXTENSIONS']


class ConvertJsonToIsaTab(Resource):

    def post(self):
        response = Response(status=415)
        if request.mimetype == "application/json":
            json = request.get_json()
            converter = JsonToIsatabWriter()
            # write the json to somewhere input_file
            unique_filename = str(uuid.uuid4()) + ".json"
            ul_dir = app.config['UPLOAD_FOLDER']
            json_file_path = os.path.join(ul_dir, unique_filename)
            fd = os.open(json_file_path, os.O_CREATE | os. os.O_RDWR)
            os.write(fd, json)
            tab_dir = os.path.join(ul_dir, unique_filename)
            os.mkdir(tab_dir)
            # Use converter to generate tab files
            converter.parsingJsonCombinedFile(json_file_path, tab_dir)
            # Zip and send back genereated tab directory

            # Right now this just echos back the json received
            return jsonify(json)
        else:
            return response


class ConvertIsaTabToJson(Resource):

    def post(self):
        response = Response(status=415)
        if request.mimetype == "multipart/form-data":
            # Unzip the file and figure out if it's an XML archive or ISArchive
            f = request.files.get('file')
            if f and allowed_file(f.filename):
                filename = secure_filename(f.filename)  # prevent malicious filenames
                unique_filename = str(uuid.uuid4())
                ul_dir = app.config['UPLOAD_FOLDER']
                temp_dir = os.path.join(ul_dir, unique_filename)
                os.mkdir(temp_dir)
                zip_path = os.path.join(temp_dir, filename)
                f.save(os.path.join(temp_dir, filename))
                with ZipFile(zip_path, 'r') as zip:
                    # extract ISArchive files
                    zip.extractall(temp_dir)
                    writer = IsatabToJsonWriter()
                    json_sub_dir = os.path.splitext(zip.filename)[0] + "-json"
                    json_dir = os.path.join(temp_dir, json_sub_dir)
                    os.mkdir(json_dir)
                    src_dir = os.path.normpath(os.path.join(temp_dir, zip.filelist[0].filename))
                    writer.parsingIsatab(src_dir, json_dir)
                    # zip and build response of converted stuff
                    # first clean up the junk expanded files
                    for f in glob.glob(json_sub_dir + "/*_expanded.json"):
                        os.remove(f)
                    # return just the combined JSON
                    combined_json_file = os.path.join(json_dir, os.path.normpath(zip.filelist[0].filename) + ".json")
                    combined_json = json.load(open(combined_json_file))
                    # cleanup generated directories
                    shutil.rmtree(temp_dir, ignore_errors=True)
                response = jsonify(combined_json)
        return response


class ConvertSraToIsaTab:
    # TODO: Implement SRA conversion to ISA-Tab
    pass