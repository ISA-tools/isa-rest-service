from flask import Flask, Response, request, jsonify
from api.io.alfie.isatabToJsonWriterV2 import IsatabToJsonWriterV2
from api.io.alfie.isaJsonToTabWriter import IsajsonToIsatabWriter

app = Flask(__name__)

#TODO: REMOVE all parsing code and make this import from isa-api project directly. Currently contains Alfie's parsers.

@app.route('/isa-convert-to/isa-tab', methods=['POST'])
def convert_to_isa_tab():
    response = Response(status=415)
    if request.mimetype == "application/json":
        json = request.get_json()
        converter = IsajsonToIsatabWriter()
        #write the json to somewhere input_file
        input_file = "/tmp/json" #Some temporary location for the JSON received
        output_dir = "/tmp/tab" #Some temporary directory, need to zip it up
        converter.parsingJsonCombinedFile(input_file, output_dir)

        # Use converter to generate tab files
        # Zip and send back
        # Right now this just echos beck the json received
        return jsonify(json)
    else:
        return response


@app.route('/isa-convert-to/isa-json', methods=['POST'])
def convert_to_isa_json():
    response = Response(status=415)
    if request.mimetype == "application/xml":
        # It's probably SRA, so run SRA parser
        return response
    elif request.mimetype == "application/zip":
        # It's probably an ISArchive, so run ISA Tab parser
        return response
    else:
        return response


@app.route('/isa-convert-to/SRA')
def convert_to_SRA():
    return 'Convert to SRA!'

if __name__ == '__main__':
    app.run()
