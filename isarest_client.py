import requests
import json
import os


class IsaRestClient:

    def __init__(self, baseurl='http://localhost:5000', dl_folder='/tmp'):
        self.baseurl = baseurl
        self.dl_folder = dl_folder

    def convert_tab_to_json(self, zipped_tab_bytes):
        """
        :param zipped_tab: Bytes of zip file containing ISA tabs to sent to converter service
        :return: Absolute path for local JSON file returned by converter service

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient(dl_folder='tmp/')
            client.convert_tab_to_json(open('testdata/BII-S-3.zip', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/convert/tab-to-json',
                                 headers={'content-type': 'application/zip'}, data=zipped_tab_bytes, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            data = response.json()
            outpath = os.path.join(self.dl_folder, data['identifier'] + '.json')
            with open(outpath, 'w') as f:
                json.dump(data, f)
            return os.path.abspath(f.name)

    def convert_json_to_tab(self, isa_json_bytes):
        """
        :param isa_json: Bytes of zip file containing ISA tabs to sent to converter service
        :return: Absolute path for local ZIP file named out.zip returned by converter service

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient(dl_folder='tmp/')
            client.convert_json_to_tab(open('testdata/BII-S-3.json', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/convert/json-to-tab',
                                 headers={'content-type': 'application/json'}, data=isa_json_bytes, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            data = response.content
            outpath = os.path.join(self.dl_folder, 'out.zip')
            with open(outpath, 'wb') as f:
                f.write(data)
            return os.path.abspath(f.name)
