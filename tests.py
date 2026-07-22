import io
import json
import os
import stat
import tempfile
import unittest
import zipfile
from unittest.mock import ANY, patch

from api.archive import InvalidArchive, extract_validated_zip
from api.create import validate_design_config
from isarest import app


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
