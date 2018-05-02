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

from isatools.convert import isatab2json, isatab2sra, json2isatab, json2sra, sampletab2isatab, sampletab2json, \
    isatab2sampletab, json2sampletab, magetab2json
from isatools.net import mw2isa
from isatools.convert.isatab2cedar import ISATab2CEDAR
from isatools import isajson, isatab


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
        response = Response(status=415)
        if request.mimetype == "application/zip":
            tmp_dir = None
            tmp_file = None
            J = None
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
                    src_dir = os.path.normpath(tmp_dir)
                    J = isatab2json.convert(src_dir, validate_first=False, use_new_parser=True)
                    if J is None:
                        raise IOError("Could not generate JSON from input ISA-Tab")
            except Exception as e:
                print("Error: {}".format(e))
                return Response(status=500)
            finally:
                # cleanup generated directories
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    os.remove(os.path.join(config.UPLOAD_FOLDER, tmp_file))
                except:
                    pass
            response = jsonify(J)
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
                file_path = _write_request_data(request, tmp_dir, tmp_file)
                if file_path is None:
                    return Response(500)
                json2isatab.convert(open(file_path), tmp_dir)
                os.remove(file_path)
                memf = io.BytesIO()
                with zipfile.ZipFile(memf, 'w') as zf:
                    for file in os.listdir(tmp_dir):
                        zf.write(os.path.join(tmp_dir, file), file)
                memf.seek(0)
                response = send_file(memf, mimetype='application/zip')
            finally:
                # cleanup generated directories
                shutil.rmtree(tmp_dir, ignore_errors=True)
        return response


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
        response = Response(status=500)
        # Create temporary directory
        tmp_dir = _create_temp_dir()
        target_tmp_dir = _create_temp_dir()
        try:
            if tmp_dir is None or target_tmp_dir is None:
                raise IOError("Could not create temporary directory " + tmp_dir)
            if not request.mimetype == "application/zip":
                raise TypeError("Incorrect media type received. Got " + request.mimetype + ", expected application/zip")
            else:
                # Write request data to file
                file_path = _write_request_data(request, tmp_dir, 'isatab.zip')
                if file_path is None:
                    raise IOError("Could not create temporary file " + file_path)

                with zipfile.ZipFile(file_path, 'r') as z:
                    # extract ISArchive files
                    z.extractall(tmp_dir)
                    src_dir = os.path.normpath(tmp_dir)
                    # convert to SRA writes to /sra
                    isatab2sra.convert(src_dir, target_tmp_dir, validate_first=False)
                    memf = io.BytesIO()
                    with zipfile.ZipFile(memf, 'w') as zf:
                        for file in os.listdir(target_tmp_dir):
                            print("Adding {} to zip".format(os.path.join(target_tmp_dir, file)))
                            zf.write(os.path.join(target_tmp_dir, file), file)
                    memf.seek(0)
                    response = send_file(memf, mimetype='application/zip')
        except TypeError as t:
            print("TypeError: {}".format(t))
            response = Response(status=415)
        except Exception as e:
            print("Error: {}".format(e))
            response = Response(status=500)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            shutil.rmtree(target_tmp_dir, ignore_errors=True)
            return response


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

                with zipfile.ZipFile(file_path, 'r') as z:
                    # extract ISArchive files
                    z.extractall(tmp_dir)
                    src_file_path = os.path.normpath(os.path.join(tmp_dir, z.filelist[0].filename))
                    # find just the combined JSON
                    with open(src_file_path) as json_fp:
                        json2sra.convert(json_fp, target_tmp_dir, validate_first=False)
                        memf = io.BytesIO()
                        with zipfile.ZipFile(memf, 'w') as zf:
                            for file in os.listdir(target_tmp_dir):
                                print("Adding {} to zip".format(os.path.join(target_tmp_dir, file)))
                                zf.write(os.path.join(target_tmp_dir, file), file)
                        memf.seek(0)
                        response = send_file(memf, mimetype='application/zip')
        except TypeError as t:
            print("TypeError: {}".format(t))
            response = Response(status=415)
        except Exception as e:
            print("Error: {}".format(e))
            response = Response(status=500)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            shutil.rmtree(target_tmp_dir, ignore_errors=True)
            return response


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
                    src_dir = os.path.normpath(tmp_dir)
                    tab2cedar = ISATab2CEDAR('http://www.isa-tools.org/')
                    tab2cedar.createCEDARjson(src_dir, src_dir, True)
                    # return just the combined JSON
                    files = [f for f in os.listdir(src_dir) if f.endswith('.json')]
                    if len(files) == 1:  # current assumption is that only one JSON should exist to know what to return
                        combined_json_file = os.path.join(src_dir, files[0])
                        combined_json = json.load(open(combined_json_file))
                    else:
                        raise IOError("More than one .json was output - cannot disambiguate what to return")
            except Exception as e:
                print("Error: {}".format(e))
                return Response(status=500)
            finally:
                # cleanup generated directories
                shutil.rmtree(tmp_dir, ignore_errors=True)
                os.remove(os.path.join(config.UPLOAD_FOLDER, tmp_file))
            response = jsonify(combined_json)
        return response


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
        response = Response(status=415)
        if request.mimetype == "application/json":
            tmp_file = str(uuid.uuid4()) + ".json"
            tmp_dir = _create_temp_dir()
            try:
                # Write request data to file
                file_path = _write_request_data(request, tmp_dir, tmp_file)
                if file_path is None:
                    return Response(500)
                result = isajson.validate(open(file_path))
                response = jsonify(result)
            except Exception:
                response = Response(status=500)
            finally:
                # cleanup generated directories
                shutil.rmtree(tmp_dir, ignore_errors=True)
        return response


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
        response = Response(status=415)
        if request.mimetype == "application/zip":
            tmp_dir = _create_temp_dir()
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
                    with zipfile.ZipFile(file_path, 'r') as z:
                        # extract ISArchive files
                        z.extractall(tmp_dir)
                        i_file_list = [i.filename for i in z.filelist if 'i_' in i.filename and i.filename.endswith('.txt')]
                        if len(i_file_list) == 1:
                            src_file_path = os.path.normpath(os.path.join(tmp_dir, i_file_list[0]))
                            fp = open(src_file_path)
                            # find just the combined JSON
                            result = isatab.validate(fp)
                            response = jsonify(result)
                        else:
                            raise Exception("Could not resolve investigation file entry point")
            except Exception:
                response = Response(status=500)
            finally:
                # cleanup generated directories
                shutil.rmtree(tmp_dir, ignore_errors=True)
        return response


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
        tmp_dir = _create_temp_dir()
        try:
            mw2isa.mw2isa_convert(studyid=studyid, outputdir=tmp_dir, dl_option="no", validate_option="no")
            memf = io.BytesIO()
            with zipfile.ZipFile(memf, 'w') as zf:
                for file in os.listdir(os.path.join(tmp_dir, studyid)):
                    print("Adding {} to zip".format(os.path.join(tmp_dir, studyid, file)))
                    zf.write(os.path.join(tmp_dir, studyid, file), file)
            memf.seek(0)
            response = send_file(memf, mimetype='application/zip')
        except Exception as e:
            print("Error: {}".format(e))
            response = Response(status=500)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return response


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
        response = Response(status=500)
        tmp_file = str(uuid.uuid4()) + ".txt"
        tmp_dir = _create_temp_dir()
        target_tmp_dir = _create_temp_dir()
        try:
            # Write request data to file
            file_path = _write_request_data(request, tmp_dir, tmp_file)
            if file_path is None:
                raise IOError("Could not create temporary file " + file_path)
            sampletab2isatab.convert(open(file_path), target_tmp_dir)
            memf = io.BytesIO()
            with zipfile.ZipFile(memf, 'w') as zf:
                for file in os.listdir(target_tmp_dir):
                    print("Adding {} to zip".format(os.path.join(target_tmp_dir, file)))
                    zf.write(os.path.join(target_tmp_dir, file), file)
            memf.seek(0)
            response = send_file(memf, mimetype='application/zip')
        except TypeError as t:
            print("TypeError: {}".format(t))
            response = Response(status=415)
        except Exception as e:
            print("Error: {}".format(e))
            response = Response(status=500)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            shutil.rmtree(target_tmp_dir, ignore_errors=True)
            return response


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
        response = Response(status=500)
        tmp_file = str(uuid.uuid4()) + ".txt"
        tmp_dir = _create_temp_dir()
        tmp_json_file = str(uuid.uuid4()) + ".json"
        try:
            # Write request data to file
            file_path = _write_request_data(request, tmp_dir, tmp_file)
            if file_path is None:
                raise IOError("Could not create temporary file " + file_path)
            with open(file_path, 'r') as input_fp:
                with open(os.path.join(tmp_dir, tmp_json_file), 'w') as json_fp:
                    sampletab2json.convert(input_fp, json_fp)
            with open(os.path.join(tmp_dir, tmp_json_file), 'r') as json_fp:
                response = jsonify(json.load(json_fp))
        except TypeError as t:
            print("TypeError: {}".format(t))
            response = Response(status=415)
        except Exception as e:
            print("Error: {}".format(e))
            response = Response(status=500)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return response


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
        response = Response(status=500)
        # Create temporary directory
        tmp_dir = _create_temp_dir()
        target_tmp_dir = _create_temp_dir()
        try:
            if tmp_dir is None:
                raise IOError("Could not create temporary directory " + tmp_dir)
            if not request.mimetype == "application/json":
                raise TypeError("Incorrect media type received. Got " + request.mimetype +
                                ", expected application/json")
            else:
                # Write request data to file
                file_path = _write_request_data(request, tmp_dir, 'in.json')
                if file_path is None:
                    raise IOError("Could not create temporary file " + file_path)
                with open(file_path) as json_fp:
                    with open(os.path.join(tmp_dir, 'out.txt'), 'w') as st_fp:
                        json2sampletab.convert(json_fp, st_fp)
                with open(os.path.join(tmp_dir, 'out.txt'), 'r') as st_fp:
                    response = send_file(st_fp, mimetype='text/tab-separated-values')
        except TypeError as t:
            print("TypeError: {}".format(t))
            response = Response(status=415)
        except Exception as e:
            print("Error: {}".format(e))
            response = Response(status=500)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            shutil.rmtree(target_tmp_dir, ignore_errors=True)
            return response


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
                file_path = _write_request_data(request, tmp_dir, 'in.zip')
                if file_path is None:
                    raise IOError("Could not create temporary file " + file_path)
                with zipfile.ZipFile(file_path, 'r') as z:
                    # extract ISArchive files
                    z.extractall(tmp_dir)
                    i_file_list = [i.filename for i in z.filelist if 'i_' in i.filename and i.filename.endswith('.txt')]
                    if len(i_file_list) == 1:
                        src_file_path = os.path.normpath(os.path.join(tmp_dir, i_file_list[0]))
                        with open(src_file_path) as fp:
                            with open(os.path.join(tmp_dir, 'out.txt'), 'w') as st_out_fp:
                                isatab2sampletab.convert(fp, st_out_fp)
                        response = send_file(os.path.join(tmp_dir, 'out.txt'), mimetype='text/tab-separated-values')
        except TypeError as t:
            print("TypeError: {}".format(t))
            response = Response(status=415)
        except Exception as e:
            print("Error: {}".format(e))
            response = Response(status=500)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            shutil.rmtree(target_tmp_dir, ignore_errors=True)
            return response


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
        response = Response(status=415)
        if request.mimetype == "application/zip":
            tmp_dir = None
            tmp_file = None
            J = None
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
                    src_dir = os.path.normpath(tmp_dir)
                    files = [f for f in os.listdir(src_dir) if f.endswith('.idf.txt')]
                    if len(files) == 1:
                        J = magetab2json.convert(os.path.join(src_dir, files[0]))
                    if J is None:
                        raise IOError("Could not generate JSON from input MAGE-TAB")
            except Exception as e:
                print("Error: {}".format(e))
                return Response(status=500)
            finally:
                # cleanup generated directories
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    os.remove(os.path.join(config.UPLOAD_FOLDER, tmp_file))
                except:
                    pass
            response = jsonify(J)
        return response


app = Flask(__name__)
app.config.from_object(config)

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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=config.PORT, debug=config.DEBUG)
