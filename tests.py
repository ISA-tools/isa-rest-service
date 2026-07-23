import copy
import importlib
import io
import json
import os
import runpy
import stat
import tempfile
import unittest
import zipfile
from contextlib import ExitStack, redirect_stdout
from unittest.mock import ANY, Mock, patch

import config as service_config
import isarest as service
import api.create as create_api
from flask import Flask
from api.archive import InvalidArchive, extract_validated_zip
from api.create import _error_response, validate_design_config
from api.validation import (
    MAX_ARMS,
    MAX_ASSAY_COMBINATIONS,
    MAX_SAMPLE_SIZE,
    MAX_SUBJECT_SIZE,
)
from isarest import app
from isarest_client import IsaRestClient
from werkzeug.exceptions import RequestEntityTooLarge


class MemberListArchive:
    """Minimal archive used for metadata rejected before extraction."""

    def __init__(self, members):
        self.members = members

    def infolist(self):
        return self.members


class ArchiveSecurityTests(unittest.TestCase):

    LIMITS = {
        'max_members': 10,
        'max_member_size': 1024,
        'max_total_size': 2048,
    }

    @staticmethod
    def make_member(
            name,
            *,
            size=0,
            compression=zipfile.ZIP_STORED,
            mode=0,
            encrypted=False
    ):
        member = zipfile.ZipInfo('placeholder')
        # Assign after construction because ZipInfo truncates names at nulls.
        member.filename = name
        member.file_size = size
        member.compress_type = compression
        member.external_attr = mode << 16
        if encrypted:
            member.flag_bits |= 0x1
        return member

    def assert_invalid(self, members, message, **limit_overrides):
        limits = dict(self.LIMITS)
        limits.update(limit_overrides)
        with tempfile.TemporaryDirectory() as destination:
            archive = MemberListArchive(members)
            with self.assertRaises(InvalidArchive) as raised:
                extract_validated_zip(archive, destination, **limits)

            self.assertEqual(str(raised.exception), message)
            self.assertEqual(os.listdir(destination), [])

    def test_extracts_stored_deflated_and_nested_files(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as archive:
            archive.writestr('empty/', b'')
            archive.writestr(
                'plain.txt', b'stored content', compress_type=zipfile.ZIP_STORED
            )
            archive.writestr(
                'nested/data.bin', b'deflated content',
                compress_type=zipfile.ZIP_DEFLATED
            )

        payload.seek(0)
        with tempfile.TemporaryDirectory() as destination:
            with zipfile.ZipFile(payload, 'r') as archive:
                extracted = extract_validated_zip(
                    archive, destination, allowed_extensions=None,
                    **self.LIMITS
                )

            self.assertTrue(os.path.isdir(os.path.join(destination, 'empty')))
            self.assertEqual(
                sorted(os.path.relpath(path, destination) for path in extracted),
                ['nested/data.bin', 'plain.txt']
            )
            with open(os.path.join(destination, 'plain.txt'), 'rb') as stored:
                self.assertEqual(stored.read(), b'stored content')
            with open(os.path.join(destination, 'nested/data.bin'), 'rb') as deflated:
                self.assertEqual(deflated.read(), b'deflated content')

    def test_extension_policy_accepts_files_and_ignores_directories(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as archive:
            archive.writestr('results/', b'')
            archive.writestr('results/REPORT.TXT', b'report')

        payload.seek(0)
        with tempfile.TemporaryDirectory() as destination:
            with zipfile.ZipFile(payload, 'r') as archive:
                extracted = extract_validated_zip(
                    archive, destination, allowed_extensions={'.txt'},
                    **self.LIMITS
                )

            self.assertEqual(len(extracted), 1)
            self.assertTrue(os.path.isfile(extracted[0]))

    def test_rejects_unsafe_member_paths(self):
        unsafe_names = (
            '', '/absolute.txt', '../escape.txt', 'safe/../../escape.txt',
            'backslash\\escape.txt', 'null\x00escape.txt', '.', 'C:/escape.txt'
        )
        for name in unsafe_names:
            with self.subTest(name=repr(name)):
                self.assert_invalid(
                    [self.make_member(name)],
                    'Archive contains an unsafe member path'
                )

    def test_rejects_encryption_and_unsupported_compression(self):
        self.assert_invalid(
            [self.make_member('secret.txt', encrypted=True)],
            'Encrypted archive members are not supported'
        )
        self.assert_invalid(
            [self.make_member('file.txt', compression=99)],
            'Archive uses an unsupported compression method'
        )

    def test_rejects_links_and_special_files(self):
        self.assert_invalid(
            [self.make_member('link.txt', mode=stat.S_IFLNK | 0o777)],
            'Archive links are not supported'
        )
        self.assert_invalid(
            [self.make_member('pipe.txt', mode=stat.S_IFIFO | 0o644)],
            'Archive contains an unsupported special file'
        )

    def test_rejects_unexpected_file_extension(self):
        with tempfile.TemporaryDirectory() as destination:
            archive = MemberListArchive([self.make_member('payload.exe')])
            with self.assertRaises(InvalidArchive) as raised:
                extract_validated_zip(
                    archive, destination, allowed_extensions={'.txt'},
                    **self.LIMITS
                )

            self.assertEqual(
                str(raised.exception),
                'Archive contains an unexpected file type'
            )
            self.assertEqual(os.listdir(destination), [])

    def test_rejects_empty_archive_and_too_many_members(self):
        self.assert_invalid([], 'Archive is empty')
        self.assert_invalid(
            [self.make_member('one.txt'), self.make_member('two.txt')],
            'Archive contains too many members', max_members=1
        )

    def test_rejects_oversized_member(self):
        self.assert_invalid(
            [self.make_member('large.txt', size=11)],
            'Archive member is too large', max_member_size=10
        )

    def test_rejects_excessive_total_size(self):
        self.assert_invalid(
            [self.make_member('one.txt', size=6),
             self.make_member('two.txt', size=5)],
            'Archive expands beyond the permitted size', max_total_size=10
        )

    def test_rejects_case_insensitive_duplicate_paths(self):
        self.assert_invalid(
            [self.make_member('Folder/File.txt'),
             self.make_member('folder/file.TXT')],
            'Archive contains duplicate member paths'
        )


class DesignConfigValidationTests(unittest.TestCase):

    @staticmethod
    def make_config():
        return {
            'arms': {
                'selected': [{'name': 'control', 'size': 10}]
            },
            'samplePlan': [{
                'sampleTypeSizes': {'control': [1]}
            }],
            'assayPlan': []
        }

    @staticmethod
    def assay(name, *nodes):
        return {'name': name, 'workflow': list(nodes)}

    @staticmethod
    def combination_node(*value_counts):
        node = {'#replicates': 1}
        for index, count in enumerate(value_counts):
            node['parameter{}'.format(index)] = {'values': list(range(count))}
        return node

    def test_validation_constants(self):
        self.assertEqual(MAX_SUBJECT_SIZE, 1000)
        self.assertEqual(MAX_ARMS, 20)
        self.assertEqual(MAX_SAMPLE_SIZE, 10000)
        self.assertEqual(MAX_ASSAY_COMBINATIONS, 32)

    def test_valid_configuration_and_none_sample_sizes(self):
        design = self.make_config()
        design['samplePlan'][0]['sampleTypeSizes']['control'] = [None, 1]
        design['assayPlan'] = [self.assay(
            'baseline',
            {'parameter': {'values': list(range(100))}},
            self.combination_node(2, 3)
        )]

        self.assertIsNone(validate_design_config(design))

    def test_rejects_too_many_arms(self):
        design = self.make_config()
        design['arms']['selected'] = [
            {'name': 'arm{}'.format(index), 'size': 1}
            for index in range(MAX_ARMS + 1)
        ]

        self.assertEqual(
            validate_design_config(design),
            {'arms': 'too many study arms. Current limit is 20, user provided 21'}
        )

    def test_rejects_oversized_arm(self):
        design = self.make_config()
        design['arms']['selected'][0]['size'] = MAX_SUBJECT_SIZE + 1

        self.assertEqual(
            validate_design_config(design),
            {'size': 'at least one group size exceeds the limit of 1000 subjects'}
        )

    def test_rejects_oversized_sample_plan(self):
        design = self.make_config()
        design['arms']['selected'][0]['size'] = MAX_SUBJECT_SIZE
        design['samplePlan'][0]['sampleTypeSizes']['control'] = [
            None, MAX_SAMPLE_SIZE // MAX_SUBJECT_SIZE + 1
        ]

        self.assertEqual(
            validate_design_config(design),
            {'sampleSize': 'at least one sample plan exceeds the limit of maximum sample size'}
        )

    def test_assay_combination_boundaries(self):
        for combinations in (
                MAX_ASSAY_COMBINATIONS - 1,
                MAX_ASSAY_COMBINATIONS
        ):
            with self.subTest(combinations=combinations):
                design = self.make_config()
                design['assayPlan'] = [self.assay(
                    'within-limit', self.combination_node(combinations)
                )]
                self.assertIsNone(validate_design_config(design))

        design = self.make_config()
        design['assayPlan'] = [self.assay(
            'over-limit', self.combination_node(MAX_ASSAY_COMBINATIONS + 1)
        )]
        self.assertEqual(
            validate_design_config(design),
            {'assayPlan': {
                'over-limit':
                    'assay exceeds maximum type of 32 allowed combinations: 33'
            }}
        )

    def test_reports_multiple_oversized_assay_types(self):
        design = self.make_config()
        design['assayPlan'] = [
            self.assay('sequencing', self.combination_node(33)),
            self.assay('metabolomics', self.combination_node(6, 6)),
        ]

        self.assertEqual(
            validate_design_config(design),
            {'assayPlan': {
                'sequencing':
                    'assay exceeds maximum type of 32 allowed combinations: 33',
                'metabolomics':
                    'assay exceeds maximum type of 32 allowed combinations: 36'
            }}
        )

    def test_error_response_with_and_without_details(self):
        with app.app_context():
            response = _error_response(400, 'invalid input')
            detailed = _error_response(422, 'invalid design', {'arms': 'invalid'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {'status': 400, 'error': {'message': 'invalid input'}}
        )
        self.assertEqual(detailed.status_code, 422)
        self.assertEqual(
            detailed.get_json(),
            {
                'status': 422,
                'error': {
                    'message': 'invalid design',
                    'details': {'arms': 'invalid'}
                }
            }
        )


class ConfigurationTests(unittest.TestCase):

    CONFIG_KEYS = (
        'DEBUG', 'PORT', 'APP_BASE_LINK', 'UPLOAD_FOLDER',
        'MAX_CONTENT_LENGTH', 'MAX_ARCHIVE_MEMBERS',
        'MAX_ARCHIVE_MEMBER_SIZE', 'MAX_ARCHIVE_TOTAL_SIZE'
    )

    @classmethod
    def reload_with_environment(cls, environment, **overrides):
        controlled_environment = {'ENVIRONMENT': environment}
        controlled_environment.update(overrides)
        try:
            with patch.dict(os.environ, controlled_environment, clear=True):
                importlib.reload(service_config)
                values = {
                    key: getattr(service_config, key) for key in cls.CONFIG_KEYS
                }
        finally:
            # Restore module globals as well as os.environ for later tests.
            importlib.reload(service_config)
        return values

    def test_development_test_and_production_modes(self):
        original_environment = copy.deepcopy(dict(os.environ))
        for environment, expected_debug in (
                ('dev', True), ('test', False), ('production', False)
        ):
            with self.subTest(environment=environment):
                values = self.reload_with_environment(environment)
                self.assertEqual(values['DEBUG'], expected_debug)
                self.assertEqual(values['PORT'], 5000)
                self.assertEqual(values['APP_BASE_LINK'], 'http://localhost:5000')
                self.assertEqual(values['UPLOAD_FOLDER'], '/tmp')
        self.assertEqual(dict(os.environ), original_environment)

    def test_upload_folder_and_numeric_limit_overrides(self):
        original_environment = copy.deepcopy(dict(os.environ))
        values = self.reload_with_environment(
            'production',
            UPLOAD_FOLDER='/srv/isa-uploads',
            MAX_CONTENT_LENGTH='101',
            MAX_ARCHIVE_MEMBERS='102',
            MAX_ARCHIVE_MEMBER_SIZE='103',
            MAX_ARCHIVE_TOTAL_SIZE='104'
        )

        self.assertEqual(values['UPLOAD_FOLDER'], '/srv/isa-uploads')
        self.assertEqual(values['MAX_CONTENT_LENGTH'], 101)
        self.assertEqual(values['MAX_ARCHIVE_MEMBERS'], 102)
        self.assertEqual(values['MAX_ARCHIVE_MEMBER_SIZE'], 103)
        self.assertEqual(values['MAX_ARCHIVE_TOTAL_SIZE'], 104)
        self.assertEqual(dict(os.environ), original_environment)


class ApiDocumentationTests(unittest.TestCase):

    EXPECTED_PATHS = {
        '/convert/tab-to-json',
        '/convert/json-to-tab',
        '/convert/tab-to-sra',
        '/convert/json-to-sra',
        '/convert/tab-to-cedar',
        '/convert/sampletab-to-isatab',
        '/convert/sampletab-to-json',
        '/convert/json-to-sampletab',
        '/convert/isatab-to-sampletab',
        '/convert/magetab-to-json',
        '/validate/json',
        '/validate/isatab',
        '/import/mw/{studyid}',
        '/isa-study-from-design',
    }

    def test_swagger_spec_documents_all_existing_routes_and_request_model(self):
        response = app.test_client().get('/api/v1/swagger.json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/json')
        specification = response.get_json()
        self.assertEqual(specification['swagger'], '2.0')
        self.assertEqual(specification['info']['version'], '1.0.0')
        self.assertEqual(specification['basePath'], '/api/v1')
        self.assertEqual(set(specification['paths']), self.EXPECTED_PATHS)
        self.assertEqual(
            {tag['name'] for tag in specification['tags']},
            {'convert', 'validate', 'import', 'study-design'}
        )

        request_model = specification['definitions']['StudyDesignRequest']
        self.assertEqual(request_model['required'], ['studyDesignConfig'])
        self.assertEqual(
            request_model['properties']['responseFormat']['enum'],
            ['json', 'tab', 'all']
        )
        operation = specification['paths']['/isa-study-from-design']['post']
        body_parameters = [
            parameter for parameter in operation['parameters']
            if parameter['in'] == 'body'
        ]
        self.assertEqual(len(body_parameters), 1)
        self.assertEqual(
            body_parameters[0]['schema']['$ref'],
            '#/definitions/StudyDesignRequest'
        )
        import_operation = specification[
            'paths'
        ]['/import/mw/{studyid}']['get']
        self.assertEqual(import_operation.get('parameters', []), [])
        self.assertEqual(
            specification['paths']['/import/mw/{studyid}']['parameters'],
            [{
                'name': 'studyid',
                'in': 'path',
                'required': True,
                'type': 'string'
            }]
        )

    def test_swagger_ui_and_application_factory(self):
        documentation = app.test_client().get('/docs')
        self.assertEqual(documentation.status_code, 200)
        self.assertEqual(documentation.mimetype, 'text/html')
        self.assertIn(b'id="swagger-ui"', documentation.data)
        self.assertIn(b'url: "/api/v1/swagger.json"', documentation.data)

        configured_app = service.create_app({
            'TESTING': True,
            'MAX_CONTENT_LENGTH': 1234
        })
        self.assertTrue(configured_app.config['TESTING'])
        self.assertEqual(configured_app.config['MAX_CONTENT_LENGTH'], 1234)
        self.assertEqual(
            configured_app.test_client().get(
                '/api/v1/swagger.json'
            ).status_code,
            200
        )


class IsaRestClientTests(unittest.TestCase):

    BASE_URL = 'https://isa.example.test'
    PAYLOAD = b'input payload'
    JSON_RESULT = {'result': ['one', 'two']}
    BINARY_RESULT = b'output payload\x00\xff'

    @staticmethod
    def response(*, ok, status_code, content=b'', json_result=None):
        response = Mock()
        response.ok = ok
        response.status_code = status_code
        response.content = content
        response.json.return_value = json_result
        return response

    def assert_post_file_method(
            self,
            method_name,
            endpoint,
            content_type,
            output_name,
            *,
            json_output=False
    ):
        with tempfile.TemporaryDirectory() as destination:
            client = IsaRestClient(self.BASE_URL, destination)
            successful = self.response(
                ok=True,
                status_code=200,
                content=self.BINARY_RESULT,
                json_result=self.JSON_RESULT
            )
            with patch('isarest_client.requests.post', return_value=successful) as post:
                with redirect_stdout(io.StringIO()):
                    output_path = getattr(client, method_name)(self.PAYLOAD)

            post.assert_called_once_with(
                self.BASE_URL + endpoint,
                headers={'Content-type': content_type},
                data=self.PAYLOAD,
                verify=False
            )
            self.assertEqual(
                output_path, os.path.abspath(os.path.join(destination, output_name))
            )
            if json_output:
                successful.json.assert_called_once_with()
                with open(output_path) as output:
                    self.assertEqual(json.load(output), self.JSON_RESULT)
            else:
                with open(output_path, 'rb') as output:
                    self.assertEqual(output.read(), self.BINARY_RESULT)

        with tempfile.TemporaryDirectory() as destination:
            client = IsaRestClient(self.BASE_URL, destination)
            unsuccessful = self.response(ok=False, status_code=400)
            with patch('isarest_client.requests.post', return_value=unsuccessful) as post:
                with redirect_stdout(io.StringIO()):
                    result = getattr(client, method_name)(self.PAYLOAD)

            post.assert_called_once_with(
                self.BASE_URL + endpoint,
                headers={'Content-type': content_type},
                data=self.PAYLOAD,
                verify=False
            )
            self.assertIsNone(result)
            self.assertEqual(os.listdir(destination), [])

    def assert_validation_method(self, method_name, endpoint, content_type):
        client = IsaRestClient(self.BASE_URL)
        report = b'{"valid": true}'
        successful = self.response(ok=True, status_code=200, content=report)
        with patch('isarest_client.requests.post', return_value=successful) as post:
            output = io.StringIO()
            with redirect_stdout(output):
                result = getattr(client, method_name)(self.PAYLOAD)

        post.assert_called_once_with(
            self.BASE_URL + endpoint,
            headers={'Content-type': content_type},
            data=self.PAYLOAD,
            verify=False
        )
        self.assertIsNone(result)
        self.assertEqual(
            output.getvalue(),
            "HTTP response code: 200\n{}\n".format(report)
        )

        unsuccessful = self.response(ok=False, status_code=422, content=b'ignored')
        with patch('isarest_client.requests.post', return_value=unsuccessful) as post:
            output = io.StringIO()
            with redirect_stdout(output):
                result = getattr(client, method_name)(self.PAYLOAD)

        post.assert_called_once_with(
            self.BASE_URL + endpoint,
            headers={'Content-type': content_type},
            data=self.PAYLOAD,
            verify=False
        )
        self.assertIsNone(result)
        self.assertEqual(output.getvalue(), 'HTTP response code: 422\n')

    def test_constructor_defaults_and_explicit_values(self):
        default_client = IsaRestClient()
        self.assertEqual(default_client.baseurl, 'http://localhost:5000')
        self.assertEqual(default_client.dl_folder, '/tmp')

        explicit_client = IsaRestClient(self.BASE_URL, '/var/tmp/isa')
        self.assertEqual(explicit_client.baseurl, self.BASE_URL)
        self.assertEqual(explicit_client.dl_folder, '/var/tmp/isa')

    def test_convert_tab_to_json(self):
        self.assert_post_file_method(
            'convert_tab_to_json', '/api/v1/convert/tab-to-json',
            'application/zip', 'out.json', json_output=True
        )

    def test_convert_json_to_tab(self):
        self.assert_post_file_method(
            'convert_json_to_tab', '/api/v1/convert/json-to-tab',
            'application/json', 'out.zip'
        )

    def test_convert_json_to_sra(self):
        self.assert_post_file_method(
            'convert_json_to_sra', '/api/v1/convert/json-to-sra',
            'application/zip', 'out.zip'
        )

    def test_convert_tab_to_sra(self):
        self.assert_post_file_method(
            'convert_tab_to_sra', '/api/v1/convert/tab-to-sra',
            'application/zip', 'out.zip'
        )

    def test_convert_tab_to_cedar(self):
        self.assert_post_file_method(
            'convert_tab_to_cedar', '/api/v1/convert/tab-to-cedar',
            'application/zip', 'out.json', json_output=True
        )

    def test_validate_json(self):
        self.assert_validation_method(
            'validate_json', '/api/v1/validate/json', 'application/json'
        )

    def test_validate_isatab(self):
        self.assert_validation_method(
            'validate_isatab', '/api/v1/validate/isatab', 'application/zip'
        )

    def test_convert_sampletab_to_tab(self):
        self.assert_post_file_method(
            'convert_sampletab_to_tab', '/api/v1/convert/sampletab-to-isatab',
            'text/tab-separated-values', 'out.zip'
        )

    def test_convert_sampletab_to_json(self):
        self.assert_post_file_method(
            'convert_sampletab_to_json', '/api/v1/convert/sampletab-to-json',
            'text/tab-separated-values', 'out.json', json_output=True
        )

    def test_import_mw_to_tab(self):
        with tempfile.TemporaryDirectory() as destination:
            client = IsaRestClient(self.BASE_URL, destination)
            successful = self.response(
                ok=True, status_code=200, content=self.BINARY_RESULT
            )
            with patch('isarest_client.requests.get', return_value=successful) as get:
                with redirect_stdout(io.StringIO()):
                    output_path = client.import_mw_to_tab('ST000367')

            get.assert_called_once_with(
                self.BASE_URL + '/api/v1/import/mw/ST000367'
            )
            self.assertEqual(
                output_path,
                os.path.abspath(os.path.join(destination, 'out.zip'))
            )
            with open(output_path, 'rb') as output:
                self.assertEqual(output.read(), self.BINARY_RESULT)

        with tempfile.TemporaryDirectory() as destination:
            client = IsaRestClient(self.BASE_URL, destination)
            unsuccessful = self.response(ok=False, status_code=404)
            with patch('isarest_client.requests.get', return_value=unsuccessful) as get:
                with redirect_stdout(io.StringIO()):
                    result = client.import_mw_to_tab('missing')

            get.assert_called_once_with(self.BASE_URL + '/api/v1/import/mw/missing')
            self.assertIsNone(result)
            self.assertEqual(os.listdir(destination), [])

    def test_convert_tab_to_sampletab(self):
        self.assert_post_file_method(
            'convert_tab_to_sampletab', '/api/v1/convert/isatab-to-sampletab',
            'application/zip', 'out.txt'
        )

    def test_convert_json_to_sampletab(self):
        self.assert_post_file_method(
            'convert_json_to_sampletab', '/api/v1/convert/json-to-sampletab',
            'application/json', 'out.txt'
        )


class IsaRestHelperTests(unittest.TestCase):

    @staticmethod
    def zip_payload(files):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return payload.getvalue()

    def test_temporary_directory_existing_and_missing_upload_folder(self):
        with tempfile.TemporaryDirectory() as upload_folder:
            with patch.object(service.config, 'UPLOAD_FOLDER', upload_folder):
                with service._temporary_directory() as temporary:
                    self.assertEqual(os.path.dirname(temporary), upload_folder)
                    self.assertTrue(os.path.isdir(temporary))

        with tempfile.TemporaryDirectory() as parent:
            missing = os.path.join(parent, 'missing-upload-folder')
            with patch.object(service.config, 'UPLOAD_FOLDER', missing):
                with self.assertRaisesRegex(IOError, 'UPLOAD_FOLDER does not exist'):
                    service._temporary_directory()

    def test_zip_directory_empty_flat_and_nested(self):
        with tempfile.TemporaryDirectory() as directory:
            with zipfile.ZipFile(service._zip_directory(directory)) as archive:
                self.assertEqual(archive.namelist(), [])

            with open(os.path.join(directory, 'flat.txt'), 'wb') as output:
                output.write(b'flat')
            nested = os.path.join(directory, 'nested')
            os.mkdir(nested)
            with open(os.path.join(nested, 'deep.txt'), 'wb') as output:
                output.write(b'deep')

            with zipfile.ZipFile(service._zip_directory(directory)) as archive:
                self.assertEqual(
                    sorted(archive.namelist()), ['flat.txt', 'nested/deep.txt']
                )
                self.assertEqual(archive.read('flat.txt'), b'flat')
                self.assertEqual(archive.read('nested/deep.txt'), b'deep')

    def test_write_request_data_preserves_exact_bytes(self):
        request = Mock()
        request.get_data.return_value = b'payload\x00\xff'
        with tempfile.TemporaryDirectory() as directory:
            path = service._write_request_data(request, directory, 'input.bin')
            with open(path, 'rb') as input_file:
                self.assertEqual(input_file.read(), b'payload\x00\xff')
        request.get_data.assert_called_once_with()

    def test_extract_archive_valid_and_invalid_zip_files(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = os.path.join(directory, 'valid.zip')
            with open(archive_path, 'wb') as output:
                output.write(self.zip_payload({'nested/file.txt': b'content'}))
            destination = os.path.join(directory, 'output')
            os.mkdir(destination)

            extracted = service._extract_archive(
                archive_path, destination, {'.txt'}
            )
            self.assertEqual(len(extracted), 1)
            with open(extracted[0], 'rb') as input_file:
                self.assertEqual(input_file.read(), b'content')

            invalid_path = os.path.join(directory, 'invalid.zip')
            with open(invalid_path, 'wb') as output:
                output.write(b'not a zip')
            with self.assertRaisesRegex(
                    InvalidArchive, 'Request does not contain a valid ZIP archive'
            ):
                service._extract_archive(invalid_path, destination, {'.txt'})

        with patch.object(
                service.zipfile, 'ZipFile', side_effect=zipfile.LargeZipFile()
        ):
            with self.assertRaisesRegex(
                    InvalidArchive, 'Request does not contain a valid ZIP archive'
            ):
                service._extract_archive('large.zip', '/tmp', {'.txt'})

    def test_extract_request_archive_returns_directory_and_files(self):
        request = Mock()
        request.get_data.return_value = self.zip_payload({'i_study.txt': b'study'})
        with tempfile.TemporaryDirectory() as directory:
            extraction_dir, files = service._extract_request_archive(
                request, directory, {'.txt'}
            )
            self.assertEqual(extraction_dir, os.path.join(directory, 'extracted'))
            self.assertEqual(files, [os.path.join(extraction_dir, 'i_study.txt')])
            with open(files[0], 'rb') as input_file:
                self.assertEqual(input_file.read(), b'study')

    def test_error_and_conversion_error_responses(self):
        with app.app_context():
            response = service._error_response(409, 'conflict')
            with patch.object(app.logger, 'exception') as log_exception:
                conversion = service._conversion_error('converter exploded')

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json(),
            {'status': 409, 'error': {'message': 'conflict'}}
        )
        self.assertEqual(conversion.status_code, 500)
        self.assertEqual(
            conversion.get_json(),
            {'status': 500, 'error': {'message': 'Conversion failed'}}
        )
        log_exception.assert_called_once_with('converter exploded')

    def test_request_too_large_handler_through_flask(self):
        limited_app = Flask('request-size-test')
        limited_app.register_error_handler(
            RequestEntityTooLarge, service.handle_request_too_large
        )

        def oversized():
            raise RequestEntityTooLarge()

        limited_app.add_url_rule('/oversized', view_func=oversized)
        response = limited_app.test_client().get('/oversized')
        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            response.get_json(),
            {
                'status': 413,
                'error': {'message': 'Request exceeds the permitted size'}
            }
        )

    def test_main_runs_flask_with_configured_values(self):
        with patch('flask.app.Flask.run') as run:
            runpy.run_module('isarest', run_name='__main__')
        run.assert_called_once_with(
            host='0.0.0.0', port=service.config.PORT, debug=service.config.DEBUG
        )


class IsaRestHandlerTests(unittest.TestCase):

    ZIP_MIME = 'application/zip'
    JSON_MIME = 'application/json'
    SAMPLE_MIME = 'text/tab-separated-values'

    def setUp(self):
        self.client = app.test_client()

    @staticmethod
    def zip_payload(files):
        return IsaRestHelperTests.zip_payload(files)

    def assert_error(self, response, status, message):
        self.assertEqual(response.status_code, status)
        self.assertEqual(
            response.get_json(),
            {'status': status, 'error': {'message': message}}
        )

    def assert_zip_response(self, response, expected_files):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, self.ZIP_MIME)
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(
                {name: archive.read(name) for name in archive.namelist()},
                expected_files
            )

    def test_wrong_mime_type_error_envelopes(self):
        cases = (
            ('/api/v1/convert/tab-to-json', 'Expected application/zip'),
            ('/api/v1/convert/json-to-tab', 'Expected application/json'),
            ('/api/v1/convert/tab-to-sra', 'Expected application/zip'),
            ('/api/v1/convert/json-to-sra', 'Expected application/zip'),
            ('/api/v1/convert/tab-to-cedar', 'Expected application/zip'),
            ('/api/v1/validate/json', 'Expected application/json'),
            ('/api/v1/validate/isatab', 'Expected application/zip'),
            ('/api/v1/convert/sampletab-to-isatab',
             'Expected text/tab-separated-values'),
            ('/api/v1/convert/sampletab-to-json',
             'Expected text/tab-separated-values'),
            ('/api/v1/convert/json-to-sampletab', 'Expected application/json'),
            ('/api/v1/convert/isatab-to-sampletab', 'Expected application/zip'),
            ('/api/v1/convert/magetab-to-json', 'Expected application/zip'),
        )
        for path, message in cases:
            with self.subTest(path=path):
                response = self.client.post(
                    path, data=b'input', content_type='application/octet-stream'
                )
                self.assert_error(response, 415, message)

    def test_invalid_archive_errors_for_every_zip_endpoint(self):
        paths = (
            '/api/v1/convert/tab-to-json',
            '/api/v1/convert/tab-to-sra',
            '/api/v1/convert/json-to-sra',
            '/api/v1/convert/tab-to-cedar',
            '/api/v1/validate/isatab',
            '/api/v1/convert/isatab-to-sampletab',
            '/api/v1/convert/magetab-to-json',
        )
        for path in paths:
            with self.subTest(path=path):
                with patch(
                    'isarest._extract_request_archive',
                    side_effect=InvalidArchive('unsafe archive')
                ):
                    response = self.client.post(
                        path, data=b'zip', content_type=self.ZIP_MIME
                    )
                self.assert_error(response, 400, 'unsafe archive')

    def test_converter_failures_return_500_and_log(self):
        isa_zip = self.zip_payload({'i_study.txt': b'study'})
        json_zip = self.zip_payload({'study.json': b'{}'})
        mage_zip = self.zip_payload({'study.idf.txt': b'idf'})
        cases = (
            ('post', '/api/v1/convert/tab-to-json', self.ZIP_MIME, isa_zip,
             'isarest.isatab2json.convert', 'Conversion failed'),
            ('post', '/api/v1/convert/json-to-tab', self.JSON_MIME, b'{}',
             'isarest.json2isatab.convert', 'Conversion failed'),
            ('post', '/api/v1/convert/tab-to-sra', self.ZIP_MIME, isa_zip,
             'isarest.isatab2sra.convert', 'Conversion failed'),
            ('post', '/api/v1/convert/json-to-sra', self.ZIP_MIME, json_zip,
             'isarest.json2sra.convert', 'Conversion failed'),
            ('post', '/api/v1/convert/tab-to-cedar', self.ZIP_MIME, isa_zip,
             'isarest.ISATab2CEDAR', 'Conversion failed'),
            ('post', '/api/v1/validate/json', self.JSON_MIME, b'{}',
             'isarest.isajson.validate', 'Validation failed'),
            ('post', '/api/v1/validate/isatab', self.ZIP_MIME, isa_zip,
             'isarest.isatab.validate', 'Validation failed'),
            ('get', '/api/v1/import/mw/ST000001', None, None,
             'isarest.mw2isa.mw2isa_convert', 'Conversion failed'),
            ('post', '/api/v1/convert/sampletab-to-isatab', self.SAMPLE_MIME,
             b'sample', 'isarest.sampletab2isatab.convert', 'Conversion failed'),
            ('post', '/api/v1/convert/sampletab-to-json', self.SAMPLE_MIME,
             b'sample', 'isarest.sampletab2json.convert', 'Conversion failed'),
            ('post', '/api/v1/convert/json-to-sampletab', self.JSON_MIME, b'{}',
             'isarest.json2sampletab.convert', 'Conversion failed'),
            ('post', '/api/v1/convert/isatab-to-sampletab', self.ZIP_MIME,
             isa_zip, 'isarest.isatab2sampletab.convert', 'Conversion failed'),
            ('post', '/api/v1/convert/magetab-to-json', self.ZIP_MIME,
             mage_zip, 'isarest.magetab2json.convert', 'Conversion failed'),
        )
        for method, path, content_type, data, target, message in cases:
            with self.subTest(path=path):
                with patch(target, side_effect=RuntimeError('converter failed')):
                    with patch.object(app.logger, 'exception') as log_exception:
                        if method == 'get':
                            response = self.client.get(path)
                        else:
                            response = self.client.post(
                                path, data=data, content_type=content_type
                            )
                self.assert_error(response, 500, message)
                log_exception.assert_called_once()

    def test_tab_to_json_success_and_none_result(self):
        payload = self.zip_payload({'i_study.txt': b'study'})
        with patch('isarest.isatab2json.convert', return_value={'study': 1}) as convert:
            response = self.client.post(
                '/api/v1/convert/tab-to-json', data=payload,
                content_type=self.ZIP_MIME
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'study': 1})
        convert.assert_called_once()

        with patch('isarest.isatab2json.convert', return_value=None):
            response = self.client.post(
                '/api/v1/convert/tab-to-json', data=payload,
                content_type=self.ZIP_MIME
            )
        self.assert_error(response, 500, 'Conversion failed')

    def test_json_to_tab_successful_zip_contents(self):
        def convert(input_file, output_directory):
            self.assertEqual(json.load(input_file), {'study': 1})
            with open(os.path.join(output_directory, 'i_generated.txt'), 'wb') as output:
                output.write(b'generated tab')

        with patch('isarest.json2isatab.convert', side_effect=convert):
            response = self.client.post(
                '/api/v1/convert/json-to-tab', data=b'{"study": 1}',
                content_type=self.JSON_MIME
            )
        self.assert_zip_response(response, {'i_generated.txt': b'generated tab'})

    def test_tab_to_sra_successful_zip_contents(self):
        def convert(_source, output_directory, validate_first):
            self.assertFalse(validate_first)
            with open(os.path.join(output_directory, 'study.xml'), 'wb') as output:
                output.write(b'<study/>')

        with patch('isarest.isatab2sra.convert', side_effect=convert):
            response = self.client.post(
                '/api/v1/convert/tab-to-sra',
                data=self.zip_payload({'i_study.txt': b'study'}),
                content_type=self.ZIP_MIME
            )
        self.assert_zip_response(response, {'study.xml': b'<study/>'})

    def test_json_to_sra_requires_one_json_and_returns_output_zip(self):
        for files in (
                {'data.csv': b'data'},
                {'one.json': b'{}', 'two.json': b'{}'}
        ):
            with self.subTest(files=tuple(files)):
                response = self.client.post(
                    '/api/v1/convert/json-to-sra', data=self.zip_payload(files),
                    content_type=self.ZIP_MIME
                )
                self.assert_error(
                    response, 400, 'Archive must contain exactly one JSON file'
                )

        def convert(input_file, output_directory, validate_first):
            self.assertEqual(json.load(input_file), {'study': 1})
            self.assertFalse(validate_first)
            with open(os.path.join(output_directory, 'experiment.xml'), 'wb') as output:
                output.write(b'<experiment/>')

        with patch('isarest.json2sra.convert', side_effect=convert):
            response = self.client.post(
                '/api/v1/convert/json-to-sra',
                data=self.zip_payload({'study.json': b'{"study": 1}'}),
                content_type=self.ZIP_MIME
            )
        self.assert_zip_response(response, {'experiment.xml': b'<experiment/>'})

    def test_tab_to_cedar_zero_one_and_multiple_json_outputs(self):
        payload = self.zip_payload({'i_study.txt': b'study'})
        for count in (0, 1, 2):
            with self.subTest(count=count):
                cedar = Mock()

                def create(source, _target, combined):
                    self.assertTrue(combined)
                    for index in range(count):
                        with open(os.path.join(source, 'cedar{}.json'.format(index)), 'w') as output:
                            json.dump({'cedar': index}, output)

                cedar.createCEDARjson.side_effect = create
                with patch('isarest.ISATab2CEDAR', return_value=cedar):
                    response = self.client.post(
                        '/api/v1/convert/tab-to-cedar', data=payload,
                        content_type=self.ZIP_MIME
                    )
                if count == 1:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.get_json(), {'cedar': 0})
                else:
                    self.assert_error(response, 500, 'Conversion failed')

    def test_json_validation_success(self):
        with patch('isarest.isajson.validate', return_value={'valid': True}) as validate:
            response = self.client.post(
                '/api/v1/validate/json', data=b'{"study": 1}',
                content_type=self.JSON_MIME
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'valid': True})
        validate.assert_called_once()

    def test_isatab_validation_investigation_file_cardinality_and_success(self):
        for files in (
                {'s_study.txt': b'study'},
                {'i_one.txt': b'one', 'i_two.txt': b'two'}
        ):
            with self.subTest(files=tuple(files)):
                response = self.client.post(
                    '/api/v1/validate/isatab', data=self.zip_payload(files),
                    content_type=self.ZIP_MIME
                )
                self.assert_error(
                    response, 400,
                    'Archive must contain exactly one investigation file'
                )

        with patch('isarest.isatab.validate', return_value={'valid': True}) as validate:
            response = self.client.post(
                '/api/v1/validate/isatab',
                data=self.zip_payload({'i_study.txt': b'study'}),
                content_type=self.ZIP_MIME
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'valid': True})
        validate.assert_called_once()

    def test_metabolomics_workbench_successful_zip(self):
        def convert(studyid, outputdir, **options):
            self.assertEqual(options, {'dl_option': 'no', 'validate_option': 'no'})
            study_directory = os.path.join(outputdir, studyid)
            os.mkdir(study_directory)
            with open(os.path.join(study_directory, 'i_study.txt'), 'wb') as output:
                output.write(b'imported')

        with patch('isarest.mw2isa.mw2isa_convert', side_effect=convert):
            response = self.client.get('/api/v1/import/mw/ST000367')
        self.assert_zip_response(response, {'i_study.txt': b'imported'})

    def test_sampletab_conversion_successes(self):
        def to_tab(input_file, output_directory):
            self.assertEqual(input_file.read(), 'sample')
            with open(os.path.join(output_directory, 'i_sample.txt'), 'wb') as output:
                output.write(b'tab')

        with patch('isarest.sampletab2isatab.convert', side_effect=to_tab):
            response = self.client.post(
                '/api/v1/convert/sampletab-to-isatab', data=b'sample',
                content_type=self.SAMPLE_MIME
            )
        self.assert_zip_response(response, {'i_sample.txt': b'tab'})

        def to_json(input_file, output_file):
            self.assertEqual(input_file.read(), 'sample')
            json.dump({'sample': 1}, output_file)

        with patch('isarest.sampletab2json.convert', side_effect=to_json):
            response = self.client.post(
                '/api/v1/convert/sampletab-to-json', data=b'sample',
                content_type=self.SAMPLE_MIME
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'sample': 1})

    def test_json_to_sampletab_successful_exact_text(self):
        def convert(input_file, output_file):
            self.assertEqual(json.load(input_file), {'study': 1})
            output_file.write('Sample Name\tFactor\nS1\tcontrol\n')

        with patch('isarest.json2sampletab.convert', side_effect=convert):
            response = self.client.post(
                '/api/v1/convert/json-to-sampletab', data=b'{"study": 1}',
                content_type=self.JSON_MIME
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, self.SAMPLE_MIME)
        self.assertEqual(response.data, b'Sample Name\tFactor\nS1\tcontrol\n')

    def test_isatab_to_sampletab_cardinality_and_success(self):
        for files in (
                {'s_study.txt': b'study'},
                {'i_one.txt': b'one', 'i_two.txt': b'two'}
        ):
            with self.subTest(files=tuple(files)):
                response = self.client.post(
                    '/api/v1/convert/isatab-to-sampletab',
                    data=self.zip_payload(files), content_type=self.ZIP_MIME
                )
                self.assert_error(
                    response, 400,
                    'Archive must contain exactly one investigation file'
                )

        def convert(input_file, output_file):
            self.assertEqual(input_file.read(), 'study')
            output_file.write('Sample Name\nS1\n')

        with patch('isarest.isatab2sampletab.convert', side_effect=convert):
            response = self.client.post(
                '/api/v1/convert/isatab-to-sampletab',
                data=self.zip_payload({'i_study.txt': b'study'}),
                content_type=self.ZIP_MIME
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, self.SAMPLE_MIME)
        self.assertEqual(response.data, b'Sample Name\nS1\n')

    def test_magetab_to_json_cardinality_none_and_success(self):
        for files in (
                {'study.sdrf.txt': b'sdrf'},
                {'one.idf.txt': b'one', 'two.idf.txt': b'two'}
        ):
            with self.subTest(files=tuple(files)):
                response = self.client.post(
                    '/api/v1/convert/magetab-to-json',
                    data=self.zip_payload(files), content_type=self.ZIP_MIME
                )
                self.assert_error(
                    response, 400, 'Archive must contain exactly one IDF file'
                )

        payload = self.zip_payload({'study.idf.txt': b'idf'})
        with patch('isarest.magetab2json.convert', return_value=None):
            response = self.client.post(
                '/api/v1/convert/magetab-to-json', data=payload,
                content_type=self.ZIP_MIME
            )
        self.assert_error(response, 500, 'Conversion failed')

        with patch(
            'isarest.magetab2json.convert', return_value={'investigation': 1}
        ) as convert:
            response = self.client.post(
                '/api/v1/convert/magetab-to-json', data=payload,
                content_type=self.ZIP_MIME
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'investigation': 1})
        convert.assert_called_once()


class StudyDesignEndpointTests(unittest.TestCase):

    PATH = '/api/v1/isa-study-from-design'
    DESIGN = {'design': 'minimal'}

    def setUp(self):
        self.client = app.test_client()

    def assert_error(self, response, status, message, details=ANY):
        self.assertEqual(response.status_code, status)
        payload = response.get_json()
        self.assertEqual(payload['status'], status)
        self.assertEqual(payload['error']['message'], message)
        if details is ANY:
            self.assertNotIn('details', payload['error'])
        else:
            self.assertEqual(payload['error']['details'], details)

    @staticmethod
    def write_tab(_investigation, output_path):
        with open(os.path.join(output_path, 'i_generated.txt'), 'w') as output:
            output.write('Investigation Identifier\tgenerated\n')

    def test_rejects_non_json_malformed_and_non_object_requests(self):
        response = self.client.post(
            self.PATH, data=b'plain text', content_type='text/plain'
        )
        self.assert_error(
            response,
            415,
            create_api.UNSUPPORTED_MIME_TYPE_ERROR.format('text/plain').strip()
        )

        response = self.client.post(
            self.PATH, data=b'{', content_type='application/json'
        )
        self.assert_error(
            response, 400, 'Request body must contain a JSON object'
        )

        response = self.client.post(self.PATH, json=['not', 'an', 'object'])
        self.assert_error(
            response, 400, 'Request body must contain a JSON object'
        )

    def test_missing_design_and_unsupported_response_format(self):
        response = self.client.post(
            self.PATH, json={'responseFormat': 'json'}
        )
        self.assert_error(
            response,
            400,
            create_api.MISSING_PARAM_ERROR.format('studyDesignConfig').strip(),
            "'studyDesignConfig'"
        )

        response = self.client.post(
            self.PATH,
            json={'studyDesignConfig': self.DESIGN, 'responseFormat': 'yaml'}
        )
        self.assert_error(
            response, 400, 'Unsupported responseFormat', 'yaml'
        )

    def test_validation_error_has_structured_details(self):
        validation_errors = {
            'arms': 'too many arms',
            'assayPlan': {'sequencing': 'too many combinations'}
        }
        with patch(
            'api.create.validate_design_config', return_value=validation_errors
        ) as validate:
            response = self.client.post(
                self.PATH,
                json={
                    'studyDesignConfig': self.DESIGN,
                    'responseFormat': 'json'
                }
            )

        self.assert_error(
            response,
            400,
            'Invalid study design configuration',
            validation_errors
        )
        validate.assert_called_once_with(self.DESIGN)

    def test_successful_json_tab_and_all_responses(self):
        for response_format in ('json', 'tab', 'all'):
            with self.subTest(response_format=response_format):
                generated_study = Mock()
                generated_study.generate_isa_study.return_value = 'isa-study'
                investigation = {'studies': ['isa-study']}
                with patch(
                    'api.create.validate_design_config', return_value=None
                ) as validate, patch(
                    'api.create.generate_study_design',
                    return_value=generated_study
                ) as generate, patch(
                    'api.create.Investigation', return_value=investigation
                ) as investigation_class, patch(
                    'api.create.isatab.dump', side_effect=self.write_tab
                ) as dump:
                    response = self.client.post(
                        self.PATH,
                        json={
                            'studyDesignConfig': self.DESIGN,
                            'responseFormat': response_format
                        }
                    )

                self.assertEqual(response.status_code, 200)
                validate.assert_called_once_with(self.DESIGN)
                generate.assert_called_once_with({
                    **self.DESIGN,
                    'design': self.DESIGN
                })
                generated_study.generate_isa_study.assert_called_once_with()
                investigation_class.assert_called_once_with(studies=['isa-study'])

                if response_format == 'json':
                    self.assertEqual(response.mimetype, 'application/json')
                    self.assertEqual(response.get_json(), investigation)
                    dump.assert_not_called()
                    continue

                self.assertEqual(response.mimetype, 'application/zip')
                with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                    names = set(archive.namelist())
                    self.assertEqual(
                        archive.read('i_generated.txt'),
                        b'Investigation Identifier\tgenerated\n'
                    )
                    if response_format == 'tab':
                        self.assertEqual(names, {'i_generated.txt'})
                    else:
                        self.assertEqual(
                            names, {'i_generated.txt', 'investigation.json'}
                        )
                        self.assertEqual(
                            json.loads(archive.read('investigation.json')),
                            investigation
                        )
                dump.assert_called_once_with(
                    investigation, output_path=ANY
                )

    def test_generation_stage_failures_return_generic_500_and_log(self):
        cases = (
            ('study generation', 'json'),
            ('ISA generation', 'json'),
            ('JSON serialization', 'json'),
            ('ISA-Tab serialization', 'tab'),
            ('ZIP creation', 'tab'),
        )
        for stage, response_format in cases:
            with self.subTest(stage=stage):
                generated_study = Mock()
                generated_study.generate_isa_study.return_value = 'isa-study'
                with ExitStack() as stack:
                    stack.enter_context(patch(
                        'api.create.validate_design_config', return_value=None
                    ))
                    generate = stack.enter_context(patch(
                        'api.create.generate_study_design',
                        return_value=generated_study
                    ))
                    stack.enter_context(patch(
                        'api.create.Investigation',
                        return_value={'studies': ['isa-study']}
                    ))
                    dump = stack.enter_context(patch(
                        'api.create.isatab.dump', side_effect=self.write_tab
                    ))
                    log_exception = stack.enter_context(
                        patch.object(app.logger, 'exception')
                    )

                    if stage == 'study generation':
                        generate.side_effect = RuntimeError('generation failed')
                    elif stage == 'ISA generation':
                        generated_study.generate_isa_study.side_effect = RuntimeError(
                            'ISA generation failed'
                        )
                    elif stage == 'JSON serialization':
                        stack.enter_context(patch(
                            'api.create.ISAJSONEncoder',
                            side_effect=RuntimeError('JSON failed')
                        ))
                    elif stage == 'ISA-Tab serialization':
                        dump.side_effect = RuntimeError('ISA-Tab failed')
                    else:
                        stack.enter_context(patch(
                            'api.create.ZipFile',
                            side_effect=RuntimeError('ZIP failed')
                        ))

                    response = self.client.post(
                        self.PATH,
                        json={
                            'studyDesignConfig': self.DESIGN,
                            'responseFormat': response_format
                        }
                    )

                self.assert_error(
                    response, 500, 'Study design generation failed'
                )
                log_exception.assert_called_once_with(
                    'Could not generate a study from the supplied design'
                )


class BaseConverterTestCase(unittest.TestCase):
    """Base test case for testing the converters"""
    def setUp(self):
        self.app = app.test_client()
        with open(os.path.join(os.path.dirname(__file__), 'testdata/BII-S-3.zip'), 'rb') as fp:
            self.test_data_zip = fp.read()
        with open(os.path.join(os.path.dirname(__file__), 'testdata/BII-S-3.json'), 'rb') as fp:
            self.test_data_json = fp.read()
        with open(os.path.join(os.path.dirname(__file__), 'testdata/BII-S-3_json.zip'), 'rb') as fp:
            self.test_data_json_zip = fp.read()
        with open(os.path.join(os.path.dirname(__file__), 'testdata/GSB-3.txt'), 'rb') as fp:
            self.test_sampletab = fp.read()
        with open(os.path.join(os.path.dirname(__file__), 'testdata/E-MEXP-31.zip'), 'rb') as fp:
            self.test_magetab_zip = fp.read()

    def tearDown(self):
        pass


class TabToJsonConverterTests(BaseConverterTestCase):

    def test_convert(self):
        response = self.app.post(path='/api/v1/convert/tab-to-json', data=self.test_data_zip,
                                 headers={'Content-Type': 'application/zip'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/json')

    def test_unsupported_content(self):
        response = self.app.post(path='/api/v1/convert/tab-to-json', data=self.test_data_json,
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 415)


class JsonToTabConverterTests(BaseConverterTestCase):

    def test_convert(self):
        response = self.app.post(path='/api/v1/convert/json-to-tab', data=self.test_data_json,
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/zip')

    def test_unsupported_mimetype(self):
        response = self.app.post(path='/api/v1/convert/json-to-tab', data=self.test_data_zip,
                                 headers={'Content-Type': 'application/zip'})
        self.assertEqual(response.status_code, 415)


class TabToSraXmlConverterTests(BaseConverterTestCase):

    def test_convert(self):
        response = self.app.post(path='/api/v1/convert/tab-to-sra', data=self.test_data_zip,
                                 headers={'Content-Type': 'application/zip'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/zip')

    def test_unsupported_content(self):
        response = self.app.post(path='/api/v1/convert/tab-to-sra', data=self.test_data_json,
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 415)


class JsonToSraXmlConverterTests(BaseConverterTestCase):

    def test_convert(self):
        response = self.app.post(path='/api/v1/convert/json-to-sra', data=self.test_data_json_zip,
                                 headers={'Content-Type': 'application/zip'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/zip')

    def test_unsupported_content(self):
        response = self.app.post(path='/api/v1/convert/json-to-sra', data=self.test_data_json,
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 415)


class TabToCedarConverterTests(BaseConverterTestCase):

    def test_convert(self):
        response = self.app.post(path='/api/v1/convert/tab-to-cedar', data=self.test_data_zip,
                                 headers={'Content-Type': 'application/zip'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/json')

    def test_unsupported_content(self):
        response = self.app.post(path='/api/v1/convert/tab-to-cedar', data=self.test_data_json,
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 415)


class IsaJsonValidatorTests(BaseConverterTestCase):

    def test_validate(self):
        response = self.app.post(path='/api/v1/validate/json', data=self.test_data_json,
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/json')

    def test_unsupported_content(self):
        response = self.app.post(path='/api/v1/validate/json', data=self.test_data_json_zip,
                                 headers={'Content-Type': 'application/zip'})
        self.assertEqual(response.status_code, 415)


class IsaTabValidatorTests(BaseConverterTestCase):

    def test_validate(self):
        response = self.app.post(path='/api/v1/validate/isatab', data=self.test_data_zip,
                                 headers={'Content-Type': 'application/zip'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/json')

    def test_unsupported_content(self):
        response = self.app.post(path='/api/v1/validate/isatab', data=self.test_data_zip,
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 415)


class ImportMWTests(BaseConverterTestCase):

    @patch('isarest.mw2isa.mw2isa_convert')
    def test_import_mw2isatab(self, mock_convert):
        def create_study(studyid, outputdir, **_kwargs):
            study_dir = os.path.join(outputdir, studyid)
            os.mkdir(study_dir)
            with open(os.path.join(study_dir, 'i_{}.txt'.format(studyid)), 'w') as output:
                output.write('Investigation Identifier\t{}\n'.format(studyid))

        mock_convert.side_effect = create_study
        response = self.app.get(path='/api/v1/import/mw/ST000367')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/zip')
        mock_convert.assert_called_once_with(
            studyid='ST000367',
            outputdir=ANY,
            dl_option='no',
            validate_option='no'
        )

    def test_unknown_resource(self):
        response = self.app.post(path='/api/v1/import/mw/ST0001')
        self.assertEqual(response.status_code, 405)


class SampleTabTests(BaseConverterTestCase):

    def test_convert_sampletab2isatab(self):
        response = self.app.post(path='/api/v1/convert/sampletab-to-isatab', data=self.test_sampletab,
                                 headers={'Content-Type': 'text/tab-separated-values'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/zip')

    def test_convert_sampletab2json(self):
        response = self.app.post(path='/api/v1/convert/sampletab-to-json', data=self.test_sampletab,
                                 headers={'Content-Type': 'text/tab-separated-values'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/json')

    def test_convert_isatab2sampletab(self):
        response = self.app.post(path='/api/v1/convert/isatab-to-sampletab', data=self.test_data_zip,
                                 headers={'Content-Type': 'application/zip'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/tab-separated-values')

    def test_convert_json2sampletab(self):
        response = self.app.post(path='/api/v1/convert/json-to-sampletab', data=self.test_data_json,
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/tab-separated-values')


class MageTabTests(BaseConverterTestCase):

    # Comment out teste because of not yet implemented services
    #
    # def test_convert_magetab2isatab(self):
    #     response = self.app.post(path='/api/v1/convert/magetab-to-isatab', data=self.test_magetab_zip,
    #                              headers={'Content-Type': 'application/zip'})
    #     self.assertEqual(response.status_code, 200)
    #     self.assertEqual(response.mimetype, 'application/zip')
    #

    def test_convert_magetab2json(self):
        response = self.app.post(path='/api/v1/convert/magetab-to-json', data=self.test_magetab_zip,
                                 headers={'Content-Type': 'application/zip'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/json')

    #
    # def test_convert_isatab2magetab(self):
    #     response = self.app.post(path='/api/v1/convert/isatab-to-magetab', data=self.test_data_zip,
    #                              headers={'Content-Type': 'application/zip'})
    #     self.assertEqual(response.status_code, 200)
    #     self.assertEqual(response.mimetype, 'application/zip')

    # def test_convert_json2magetab(self):
    #     response = self.app.post(path='/api/v1/convert/json-to-magetab', data=self.test_data_json,
    #                              headers={'Content-Type': 'application/json'})
    #     self.assertEqual(response.status_code, 200)
    #     self.assertEqual(response.mimetype, 'application/zip')


class ISAStudyDesignTest(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        with open(os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                'testdata',
                'study-design-config',
                'crossover-study-design-4-arms-blood-derma-nmr-ms.json'
            )
        )) as fp:
            self.design_config = json.load(fp)

    def test_validate_design_config(self):
        res = validate_design_config(self.design_config)
        self.assertIsNone(res)

    def test_send_isa_json(self):
        req_data = dict(responseFormat='json', studyDesignConfig=self.design_config)
        response = self.app.post(
            path='/api/v1/isa-study-from-design',
            json=req_data
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/json')

    def test_send_isa_tab(self):
        response = self.app.post(
            path='/api/v1/isa-study-from-design',
            json=dict(responseFormat='tab', studyDesignConfig=self.design_config)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/zip')

    def test_send_isa_json_and_tab(self):
        response = self.app.post(
            path='/api/v1/isa-study-from-design',
            json=dict(responseFormat='all', studyDesignConfig=self.design_config)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/zip')


if __name__ == '__main__':
    unittest.main()
