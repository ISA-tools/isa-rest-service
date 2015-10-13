import unittest

from isarestapi import run


class TestIsaApi(unittest.TestCase):

    def setUp(self):
        self.app = run.app.test_client()
        self.fileobj = open('data/BII-I-1.zip', 'rb')
        json_fileobj = open('data/BII-I-1.json', 'rb')
        self.json = json_fileobj.read()

    def tearDown(self):
        pass

    def test_convert_to_isajson(self):
        response = self.app.post(path='/convert/to-isa-json', data={'file': (self.fileobj, 'BII-I-1.zip')})
        assert(response.status_code == 200)
        assert(response.mimetype == 'application/json')
        # TODO Validate what's returned is correct based on what we sent
        print(response.data)

    def test_convert_to_isatab(self):
        response = self.app.post(path='/convert/json-to-isatab', data=self.json, headers={'Content-Type': 'application/json'})
        assert(response.status_code == 200)
        assert(response.mimetype == 'multipart/file-data')
        # TODO Validate what's returned is correct based on what we sent
        print(response.data)

    def test_unsupported_mimetype(self):
        response = self.app.post(path='/converter/to-isa-tab', data={'file': (self.fileobj, 'BII-I-1.zip')})
        assert(response.status_code == 415)

if __name__ == '__main__':
    unittest.main()
