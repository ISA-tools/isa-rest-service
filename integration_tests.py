import unittest

from isarest import app


class MetabolomicsWorkbenchIntegrationTest(unittest.TestCase):

    def test_import_mw2isatab_live(self):
        response = app.test_client().get(path='/api/v1/import/mw/ST000367')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/zip')


if __name__ == '__main__':
    unittest.main()
