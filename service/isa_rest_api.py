import os
from flask import Flask, Response, request, jsonify
from api.io.alfie.isaJsonToTabWriter import IsajsonToIsatabWriter

app = Flask(__name__)

# TODO: REMOVE all parsing code and make this import from isa-api project directly. Currently contains Alfie's parsers.


@app.route('/isa-convert-to/isa-tab', methods=['POST'])
def convert_to_isa_tab():
    response = Response(status=415)
    if request.mimetype == "application/json":
        json = request.get_json()
        converter = IsajsonToIsatabWriter()
        # rite the json to somewhere input_file
        json_dir = "tmp/json"  # Some temporary location for the JSON received
        tab_dir = "tmp/tab"   # Some temporary directory, need to zip it up
        converter.parsingJsonCombinedFile(json_dir, tab_dir)

        # Use converter to generate tab files
        # Zip and send back
        # Right now this just echos beck the json received
        return jsonify(json)
    else:
        return response


@app.route('/isa-convert-to/isa-json', methods=['POST'])
def convert_to_isa_json():
    response = Response(status=415)
    if request.mimetype == "multipart/form-data":
        # Unzip the file and figure out if it's an XML archive or ISArchive
        f = request.files['file']
        tab_dir = "tmp/tab"
        new_file = os.path.join(os.path.join(os.path.dirname(__file__), tab_dir), f.filename)
        response = Response(status=200)
    return response


@app.route('/isa-convert-to/SRA')
def convert_to_sra():
    return 'Convert to SRA!'

if __name__ == '__main__':
    app.run()
