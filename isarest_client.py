import requests
import json
import os


class IsaRestClient:

    def __init__(self, baseurl='http://localhost:5000', dl_folder='/tmp'):
        self.baseurl = baseurl
        self.dl_folder = dl_folder

    def convert_tab_to_json(self, zipped_tab):
        """
        :param zipped_tab: Bytes of zip file containing ISA tabs to sent to converter service
        :return: Absolute path for local JSON file returned by converter service

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient(dl_folder='tmp/')
            client.convert_tab_to_json(open('testdata/BII-S-3.zip', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/convert/tab-to-json',
                                 headers={'content-type': 'application/zip'}, data=zipped_tab, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            data = response.json()
            outpath = os.path.join(self.dl_folder, data['identifier'] + '.json')
            with open(outpath, 'w') as f:
                json.dump(data, f)
            return os.path.abspath(f.name)