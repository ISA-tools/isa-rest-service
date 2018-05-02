import unittest
import os
from isarest import app


class BaseConverterTestCase(unittest.TestCase):
    """Base test case for testing the converters"""
    def setUp(self):
        self.app = app.test_client()
        self.test_data_zip = open(os.path.join(os.path.dirname(__file__), 'testdata/BII-S-3.zip'), 'rb').read()
        self.test_data_json = open(os.path.join(os.path.dirname(__file__), 'testdata/BII-S-3.json'), 'rb').read()
        self.test_data_json_zip = open(os.path.join(os.path.dirname(__file__), 'testdata/BII-S-3_json.zip'), 'rb').read()
        self.test_sampletab = open(os.path.join(os.path.dirname(__file__), 'testdata/GSB-3.txt'), 'rb').read()
        self.test_magetab_zip = open(os.path.join(os.path.dirname(__file__), 'testdata/E-MEXP-31.zip'), 'rb').read()

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


if __name__ == '__main__':
    unittest.main()
