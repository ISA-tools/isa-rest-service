import unittest
from service import isa_rest_api
__author__ = 'dj'


class TestIsaApi(unittest.TestCase):

    def setUp(self):
        self.app = isa_rest_api.app.test_client()
        self.fileobj = open('data/BII-I-1.zip', 'rb')

    def tearDown(self):
        pass

    def test_convert_to_isajson(self):
        response = self.app.post(path='/converter/to-isa-json', data={'file': (self.fileobj, 'BII-I-1.zip')})
        assert(response.status_code == 200)

    def test_unsupported_mimetype(self):
        response = self.app.post(path='/converter/to-isa-tab', data={'file': (self.fileobj, 'BII-I-1.zip')})
        assert(response.status_code == 415)

if __name__ == '__main__':
    unittest.main()
