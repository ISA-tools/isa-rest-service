import copy
import importlib
import io
import json
import os
import stat
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from unittest.mock import ANY, Mock, patch

import config as service_config
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
