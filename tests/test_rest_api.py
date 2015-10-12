import unittest

from isarestapi.app import app


class TestIsaApi(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.fileobj = open('data/BII-I-1.zip', 'rb')

    def tearDown(self):
        pass

    def test_convert_to_isajson(self):
        response = self.app.post(path='/convert/to-isa-json', data={'file': (self.fileobj, 'BII-I-1.zip')})
        assert(response.status_code == 200)
        assert(response.mimetype == 'application/json')
        # TODO Validate what's returned is correct based on what we sent
        print(response.data)

    def test_unsupported_mimetype(self):
        response = self.app.post(path='/converter/to-isa-tab', data={'file': (self.fileobj, 'BII-I-1.zip')})
        assert(response.status_code == 415)

if __name__ == '__main__':
    unittest.main()
