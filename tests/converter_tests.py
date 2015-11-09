import unittest
import os
import app


class BaseConverterTestCase(unittest.TestCase):
    """Base test case for testing the converters"""
    def setUp(self):
        self.app = app.test_client()
        self.test_data_zip = str(open(os.path.join(os.path.dirname(__file__), 'data/BII-I-1.zip'), 'rb').read())
        self.test_data_json = open(os.path.join(os.path.dirname(__file__), 'data/BII-I-1.json'), 'rb').read()

    def tearDown(self):
        # TODO: Implement any cleanup code, if necessary (e.g. temporary files when uncompressing received zips)
        pass


class TabToJsonConverterTests(BaseConverterTestCase):

    def test_convert(self):
        response = self.app.post(path='/convert/isatab-to-json', data=self.test_data_zip,
                                 headers={'Content-Type': 'application/zip'})
        assert(response.status_code == 200)
        assert(response.mimetype == 'application/json')

    def test_unsupported_content(self):
        response = self.app.post(path='/convert/isatab-to-json', data=self.test_data_json,
                                 headers={'Content-Type': 'application/json'})
        assert(response.status_code == 415)


class JsonToTabConverterTests(BaseConverterTestCase):

    def test_convert(self):
        response = self.app.post(path='/convert/json-to-isatab', data=self.json,
                                 headers={'Content-Type': 'application/json'})
        assert(response.status_code == 200)
        assert(response.mimetype == 'application/zip')

    def test_unsupported_mimetype(self):
        response = self.app.post(path='/convert/json-to-isatab', data=self.test_data_zip,
                         headers={'Content-Type': 'application/zip'})
        assert(response.status_code == 415)


class TabToSraXmlConverterTests(BaseConverterTestCase):

    def test_convert(self):
        response = self.app.post(path='/convert/isatab-to-sra', data=self.test_data_zip,
                                 headers={'Content-Type': 'application/zip'})
        assert(response.status_code == 200)
        assert(response.mimetype == 'application/xml')

    def test_unsupported_content(self):
        response = self.app.post(path='/convert/isatab-to-sra', data=self.test_data_json,
                                 headers={'Content-Type': 'application/json'})
        assert(response.status_code == 415)


class SraXmlToTabConverterTests(BaseConverterTestCase):

    def test_convert(self):
        response = self.app.post(path='/convert/sra-to-isatab', data=self.test_data_sra_xml,
                                 headers={'Content-Type': 'application/xml'})
        assert(response.status_code == 200)
        assert(response.mimetype == 'application/xml')

    def unsupported_mimetype(self):
        response = self.app.post(path='/convert/sra-to-isatab', data={'file': (self.fileobj, 'BII-I-1.zip')},
                         headers={'Content-Type': 'application/zip'})
        assert(response.status_code == 415)

# TODO: Write tests for CEDAR converters

if __name__ == '__main__':
    unittest.main()
