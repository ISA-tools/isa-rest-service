import requests
import json
import os


class IsaRestClient:

    def __init__(self, baseurl='http://localhost:5000', dl_folder='/tmp'):
        self.baseurl = baseurl
        self.dl_folder = dl_folder

    def convert_tab_to_json(self, zipped_tab_bytes):
        """
        :param zipped_tab_bytes: Bytes of zip file containing ISA tabs to sent to converter service
        :return: Absolute path for local JSON file returned by converter service called out.json

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient(dl_folder='tmp/')
            client.convert_tab_to_json(open('testdata/BII-S-3.zip', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/convert/tab-to-json',
                                 headers={'Content-type': 'application/zip'}, data=zipped_tab_bytes, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            data = response.json()
            outpath = os.path.join(self.dl_folder, 'out.json')
            with open(outpath, 'w') as f:
                json.dump(data, f)
            return os.path.abspath(f.name)

    def convert_json_to_tab(self, isa_json_bytes):
        """
        :param isa_json_bytes: Bytes of zip file containing ISA tabs to sent to converter service
        :return: Absolute path for local ZIP file named out.zip returned by converter service

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient(dl_folder='tmp/')
            client.convert_json_to_tab(open('testdata/BII-S-3.json', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/convert/json-to-tab',
                                 headers={'Content-type': 'application/json'}, data=isa_json_bytes, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            data = response.content
            outpath = os.path.join(self.dl_folder, 'out.zip')
            with open(outpath, 'wb') as f:
                f.write(data)
            return os.path.abspath(f.name)

    def convert_json_to_sra(self, isa_json_zip_bytes):
        """
        :param isa_json_zip_bytes: Bytes of zip file containing ISA JSON and data files to sent to converter service
        :return: Absolute path for local ZIP file named out.zip returned by converter service

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient(dl_folder='tmp/')
            client.convert_json_to_tab(open('testdata/BII-S-3_json.zip', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/convert/json-to-sra',
                                 headers={'Content-type': 'application/zip'}, data=isa_json_zip_bytes, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            data = response.content
            outpath = os.path.join(self.dl_folder, 'out.zip')
            with open(outpath, 'wb') as f:
                f.write(data)
            return os.path.abspath(f.name)

    def convert_tab_to_sra(self, zipped_tab_bytes):
        """
        :param isa_json_zip_bytes: Bytes of zip file containing ISA JSON and data files to sent to converter service
        :return: Absolute path for local ZIP file named out.zip returned by converter service

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient(dl_folder='tmp/')
            client.convert_json_to_tab(open('testdata/BII-S-3_json.zip', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/convert/tab-to-sra',
                                 headers={'Content-type': 'application/zip'}, data=zipped_tab_bytes, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            data = response.content
            outpath = os.path.join(self.dl_folder, 'out.zip')
            with open(outpath, 'wb') as f:
                f.write(data)
            return os.path.abspath(f.name)

    def convert_tab_to_cedar(self, zipped_tab_bytes):
        """
        :param zipped_tab_bytes: Bytes of zip file containing ISA tabs to sent to converter service
        :return: Absolute path for local CEDAR JSON file returned by converter service called out.json

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient(dl_folder='tmp/')
            client.convert_tab_to_json(open('testdata/BII-S-3.zip', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/convert/tab-to-cedar',
                                 headers={'Content-type': 'application/zip'}, data=zipped_tab_bytes, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            data = response.json()
            outpath = os.path.join(self.dl_folder, 'out.json')
            with open(outpath, 'w') as f:
                json.dump(data, f)
            return os.path.abspath(f.name)

    def validate_json(self, isa_json_bytes):
        """
        :param isa_json_bytes: Bytes of ISA JSON to sent to converter service
        :return: JSON validation report: Validation report as JSON

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient()
            client.validate_json(open('testdata/BII-S-3.json', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/validate/json',
                                 headers={'Content-type': 'application/json'}, data=isa_json_bytes, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            print(response.content)

    def validate_isatab(self, isatab_zip_bytes):
        """
        :param isatab_zip_bytes: Bytes of zip file containing ISA tabs to sent to converter service
        :return: JSON validation report: Validation report as JSON

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient()
            client.validate_tab(open('testdata/BII-S-3.zip', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/validate/isatab',
                                 headers={'Content-type': 'application/zip'}, data=isatab_zip_bytes, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            print(response.content)

    def convert_sampletab_to_tab(self, sampletab_bytes):
        """
        :param sampletab_bytes: Bytes of SampleTab input file to sent to converter service
        :return: Absolute path for local ZIP file named out.zip returned by converter service

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient(dl_folder='tmp/')
            client.convert_sampletab_to_tab(open('testdata/GSB-3.txt', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/convert/sampletab-to-isatab',
                                 headers={'Content-type': 'text/tab-separated-values'}, data=sampletab_bytes, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            data = response.content
            outpath = os.path.join(self.dl_folder, 'out.zip')
            with open(outpath, 'wb') as f:
                f.write(data)
            return os.path.abspath(f.name)

    def convert_sampletab_to_json(self, sampletab_bytes):
        """
        :param sampletab_bytes: Bytes of SampleTab input file to sent to converter service
         :return: Absolute path for local JSON file returned by converter service called out.json

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient(dl_folder='tmp/')
            client.convert_sampletab_to_json(open('testdata/GSB-3.txt', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/convert/sampletab-to-json',
                                 headers={'Content-type': 'text/tab-separated-values'}, data=sampletab_bytes, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            data = response.json()
            outpath = os.path.join(self.dl_folder, 'out.json')
            with open(outpath, 'w') as f:
                json.dump(data, f)
            return os.path.abspath(f.name)

    def import_mw_to_tab(self, accession):
        """
        :param accession: Accession ID for study in MetabolomicsWorkbench
        :return: Absolute path for local ZIP file named out.zip returned by converter service

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient(dl_folder='tmp/')
            client.import_mw_to_tab('ST000367')
        """
        response = requests.get(self.baseurl + '/api/v1/import/mw/' + accession)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            data = response.content
            outpath = os.path.join(self.dl_folder, 'out.zip')
            with open(outpath, 'wb') as f:
                f.write(data)
            return os.path.abspath(f.name)

    def convert_tab_to_sampletab(self, zipped_tab_bytes):
        """
        :param isa_json_zip_bytes: Bytes of zip file containing ISA JSON and data files to sent to converter service
        :return: Absolute path for SampleTab file named out.txt returned by converter service

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient(dl_folder='tmp/')
            client.convert_tab_to_sampletab(open('testdata/BII-S-3_json.zip', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/convert/isatab-to-sampletab',
                                 headers={'Content-type': 'application/zip'}, data=zipped_tab_bytes, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            data = response.content
            outpath = os.path.join(self.dl_folder, 'out.txt')
            with open(outpath, 'wb') as f:
                f.write(data)
            return os.path.abspath(f.name)

    def convert_json_to_sampletab(self, isa_json_bytes):
        """
        :param isa_json_bytes: Bytes of zip file containing ISA tabs to sent to converter service
        :return: Absolute path for local ZIP file named out.zip returned by converter service

        Example usage

            from isarest_client import IsaRestClient
            client = IsaRestClient(dl_folder='tmp/')
            client.convert_json_to_sampletab(open('testdata/BII-S-3.zip', 'rb').read())
        """
        response = requests.post(self.baseurl + '/api/v1/convert/json-to-sampletab',
                                 headers={'Content-type': 'application/json'}, data=isa_json_bytes, verify=False)
        print("HTTP response code: " + str(response.status_code))
        if response.ok:
            data = response.content
            outpath = os.path.join(self.dl_folder, 'out.txt')
            with open(outpath, 'wb') as f:
                f.write(data)
            return os.path.abspath(f.name)