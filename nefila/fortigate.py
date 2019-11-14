import requests
from .utils import get_credentials
import json
import time
import datetime

class FortiGate(object):
    def __init__(self, hostname):
        #: Use the same session for all requests
        self.session = requests.session()

        #: SSL Verification default.
        self.session.verify = False

        #: How long to wait for the server to send data before giving up
        self.timeout = 10

        #: Device hostname
        self.hostname = hostname
        self.base_url = f'https://{self.hostname}/api/v2'

        # Subsystems init
        self.system = System(self.session, self.timeout, self.base_url)


    def open(self, username=None, password=None, token=None, profile=None):

        # If credentials are not supplied, check file
        if not (username or token or profile):
            credentials = get_credentials(self.hostname)
            username = credentials['username']
            password = credentials['password']
            token = credentials['token']

        # Update parameters
        self.username = username
        url_login = f'https://{self.hostname}/logincheck'

        if not token:
            self.session.post(url=url_login,
                            data=f'username={username}&secretkey={password}',
                            timeout = self.timeout,
            )

            for cookie in self.session.cookies:
                if cookie.name == 'ccsrftoken':
                    csrftoken = cookie.value[1:-1]
                    self.session.headers.update({'X-CSRFTOKEN': csrftoken})

        else:
            self.session.headers.update({'Authorization': f'Bearer {token}'})
            self.token = True
        
        response = self.license_status()
        
        # self.serial = response.json()['serial']
        
        # version = response.json()['version']
        # build = str(response.json()['build'])
        # self.version = f'{version},build{build}'

        return response


    def close(self):
        url_logout = f'https://{self.hostname}/logout'
        response = self.session.post(url_logout, timeout=self.timeout)
        return response.status_code


    def _get_status(self):
        '''Obtain general status
        
        Uptime in seconds

        '''
        url = f'{self.base_url}/monitor/license/status'
        response = self.session.get(url, timeout=self.timeout)
        if response.status_code == 200:
            status = {}
            status['version'] = response.json()['version']
            status['serial'] = response.json()['serial']
            status['forticare'] = response.json()['results']['forticare']['status']

        url = f'{self.base_url}/monitor/web-ui/state'
        response = self.session.get(url, timeout=self.timeout)
        if response.status_code == 200:
            model_name = response.json()['results']['model_name']
            model_number = response.json()['results']['model_number']

            ticks = response.json()['results']['utc_last_reboot'] 
            ticks_to_seconds = ticks/1000
            uptime = time.time() - ticks_to_seconds
            uptime = datetime.timedelta(seconds=uptime)

            status['hostname'] = response.json()['results']['hostname']
            status['model'] = f'{model_name}-{model_number}'
            status['uptime'] = uptime.seconds

            return status
        else:
            return response.status_code

    @property
    def status(self):
        return self._get_status()


    def basic_status(self):
        '''Retrieve basic system status.'''
        url = f'{self.base_url}/monitor/system/status'
        response = self.session.get(url, timeout=self.timeout)
        return response


    def license_status(self):
        '''Get current license & registration status.'''
        url = f'{self.base_url}/monitor/license/status'
        response = self.session.get(url, timeout=self.timeout)

        if response.status_code == 200:
            self.version = response.json()['version']
            self.serial = response.json()['serial']
            self.forticare = response.json()['results']['forticare']['status']

        return response


class System(object):
    def __init__(self, session, timeout, base_url):
        self.session = session
        self.timeout = timeout
        self.base_url = base_url

        self.dns_database = DnsDatabase(self.session, self.timeout, self.base_url, name=None)
        self.firmware = Firmware(self.session, self.timeout, self.base_url)
        self.api_user = ApiUser(self.session, self.timeout, self.base_url, name='nefila-api-admin')
        self.interface = Interface(self.session, self.timeout, self.base_url)




class Interface(object):
    '''List and configure interfaces

    Usage:
        device.system.interface.list()
        device.system.interface.create()
        device.system.interface.get()
        device.system.interface.get(name='wan1')
        device.system.interface.delete()
    '''

    def __init__(self, session, timeout, base_url):
        self.session = session
        self.timeout = timeout
        self.base_url = base_url

    def list(self):
        '''List all interfaces'''
        url = f'{self.base_url}/monitor/system/available-interfaces'
        r = self.session.get(url=url, timeout=self.timeout)
        return r


class ApiUser(object):
    '''List and configure API users.

    Default API user is nefila-api-admin using super_admin profile and 
    trusted hosts 192.168.0.0/16.

    Usage:
        device.system.api_user.list()
        device.system.api_user.create()
        device.system.api_user.token
        device.system.api_user.get()
        device.system.api_user.delete()

        device.system.api_user.name = 'custom-api-admin'
        device.system.api_user.create(accprofile='prof_admin',
                            ipv4_trusthost='192.0.2.0/24')
    '''

    def __init__(self, session, timeout, base_url, name):
        self.session = session
        self.timeout = timeout
        self.base_url = base_url
        self.name = name

    def list(self):
        '''List all API users'''
        url = f'{self.base_url}/cmdb/system/api-user'
        response = self.session.get(url=url, timeout=self.timeout)
        return response

    def create(self, accprofile='super_admin', ipv4_trusthost='192.168.0.0/16'):
        '''Create a new API user and generate an access key'''
        url = f'{self.base_url}/cmdb/system/api-user'
        name = self.name
        token = None

        data = {
            'name': name,
            'accprofile': accprofile,
            'trusthost':[{
                'id':0,
                'type':'ipv4-trusthost',
                'ipv4-trusthost': ipv4_trusthost,
                }
            ]
        }

        response = self.session.post(url=url, json=data)

        if response.status_code == 200:
            data = {'api-user': self.name}
            url = f'{self.base_url}/monitor/system/api-user/generate-key'
            response = self.session.post(url=url, json=data)
            token = response.json()['results']['access_token']
            self.token = token

        return response

    def get(self):
        '''Get details of a specific API user'''
        url = f'{self.base_url}/cmdb/system/api-user/{self.name}'
        response = self.session.get(url=url, timeout=self.timeout)
        return response


    def delete(self):
        '''Delete API user'''
        url = f'{self.base_url}/cmdb/system/api-user/{self.name}'
        response = self.session.delete(url=url, timeout=self.timeout)
        return response


class Firmware(object):
    '''List and upgrade device firmware.

    Usage:
        device.system.firmware.list()
        device.system.firmware.upgrade()
        device.system.firmware.upgrade('v6.2.0')
        device.system.firmware.upgrade_file('./var/FGT_VM64_KVM-v6-build1510-FORTINET.out')
    '''

    def __init__(self, session, timeout, base_url):
        self.session = session
        self.timeout = timeout
        self.base_url = base_url

    def list(self):
        '''Retrieve a list of firmware images available to use for 
        upgrade on this device from FortiGuard'''
        url = f'{self.base_url}/monitor/system/firmware'
        response = self.session.get(url=url, timeout=self.timeout)
        return response

    def upgrade(self, version=None, timeout=300):
        '''Upgrade firmware image on this device
        Default timeout is longer to allow firmware download from FDN'''
        url = f'{self.base_url}/monitor/system/firmware/upgrade'
        

        firmware_list = self.list().json()['results']['available']

        if not version:
            version_id = firmware_list[0]['id']

        # If version is set, find corresponding version_id
        # If version equals None then update to the latest available
        if version:
            for firmware in firmware_list:
                if firmware['version'] == version:
                    version_id = firmware['id']
        else:
            version_id = firmware_list[0]['id']

        data = {'source': 'fortiguard', 'filename': version_id}
        response = self.session.post(url=url, json=data, timeout=timeout)

        # Should return this if success
        '''
        {'http_method': 'POST',
        'results': {'status': 'success'},
        'vdom': 'root',
        'path': 'system',
        'name': 'firmware',
        'action': 'upgrade',
        'status': 'success',
        'serial': 'FGVULVTM19000XXX',
        'version': 'v6.2.0',
        'build': 799}
        '''

        return response

    def upgrade_file(self, filename=None, timeout=300):
        '''Upgrade firmware image on this device using an uploaded file
        Default timeout is longer to allow firmware download from FDN'''
        url = f'{self.base_url}/monitor/system/firmware/upgrade'

        data = {'source': 'upload', 'scope': 'global'}
        f = open(filename, 'rb')
        firmware_file = {'file': (filename, f, 'text/plain')}

        r = self.session.post(
                            url=url,
                            data=data,
                            files=firmware_file,
                            timeout=timeout
        )

        return r


class DnsDatabase(object):
    '''Add or check records on the DNS Database.

    Usage:
        device.system.dns_database.list()
        device.system.dns_database.name = 'exampleZone'
        device.system.dns_database.create()
        device.system.dns_database.add(ip='192.2.0.1', hostname='example')
        device.system.dns_database.get().json()
        device.system.dns_database.delete()
    '''

    def __init__(self, session, timeout, base_url, name):
        self.session = session
        self.timeout = timeout
        self.base_url = base_url
        self.name = name


    def list(self):
        '''List all DNS zones'''
        url = f'{self.base_url}/cmdb/system/dns-database'
        response = self.session.get(url=url, timeout=self.timeout)
        return response


    def create(self):
        '''Create a new DNS Zone'''
        url = f'{self.base_url}/cmdb/system/dns-database'
        data = {'name': self.name, 'domain': self.name}
        response = self.session.post(url=url, json=data)
        return response

    def add(self, ip, hostname):
        '''Add a new entry on a specific existing DNS Zone, preserving 
        existing entries.
        '''
        # Obtain existing list
        url = f'{self.base_url}/cmdb/system/dns-database/{self.name}'
        response = self.session.get(url=url, timeout=self.timeout)
        dns_entry_list = response.json()['results'][0]['dns-entry']

        # prepare the new entry
        dns_entry_id = len(dns_entry_list) + 1
        dns_entry = {
                'id': dns_entry_id,
                'ip': ip,
                'hostname': hostname,
        }

        # prepare new dns table
        dns_entry_list.append(dns_entry)
        dns_entry = {'dns-entry': dns_entry_list}

        # update zone
        response = self.session.put(url, json=dns_entry)
        
        return response


    def get(self):
        '''Get all entries of a specific DNS Zone'''
        url = f'{self.base_url}/cmdb/system/dns-database/{self.name}'
        response = self.session.get(url=url, timeout=self.timeout)
        return response


    def delete(self):
        '''Delete DNS Zone'''
        url = f'{self.base_url}/cmdb/system/dns-database/{self.name}'
        response = self.session.delete(url=url, timeout=self.timeout)
        return response
