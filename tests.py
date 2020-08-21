import json
import unittest
import os
from isarest import app
from api.create import validate_design_config


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

    def test_import_mw2isatab(self):
        response = self.app.get(path='/api/v1/import/mw/ST000367')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/zip')

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
                os.path.dirname(__file__), 'testdata', 'study-design-config', 'study-design-3-repeated-treatments.json'
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
