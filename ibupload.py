#!/usr/bin/env python

import requests
import json
import glob
import os
import hashlib
import sys

sys.tracebacklimit = 0

class ServerError(Exception):
    pass
    
class ValueError(Exception):
    pass
    
class Uploader(object):
    """
    Class for uploading content to iBroadcast.
    """

    VERSION = '.1'
    CLIENT = 'python uploader script'

    def __init__(self, username, password):
        self.username = username
        self.password = password

        # Initialise our variables that each function will set.
        self.user_id = None
        self.token = None
        self.supported = None
        self.files = None
        self.md5 = None

    def process(self):
        try:
            self.login()
        except ValueError, e:
            print 'Login failed: %s' % e
            return
        self.load_files()
        if self.confirm():
            self.upload()

    def login(self, username=None, password=None):
        """
        Login to iBroadcast with the given username and password

        Raises:
            ValueError on invalid login

        """
        # Default to passed in values, but fallback to initial data.
        username = username or self.username
        password = password or self.password
        print 'Logging in...'
        # Build a request object.
        post_data = json.dumps({
            'mode' : 'status',
            'email_address': username,
            'password': password,
            'version': self.VERSION,
            'client': self.CLIENT,
            'supported_types' : 1,
        })
        response = requests.post(
            "https://json.ibroadcast.com/s/JSON/status",
            data=post_data,
            headers={'Content-Type': 'application/json'}
        )

        if not response.ok:
            raise ServerError('Server returned bad status: ',
                             response.status_code)

        jsoned = response.json()

        if 'user' not in jsoned:
            raise ValueError('Invalid login.')

        print 'Login successful - user_id: ', jsoned['user']['id']
        self.user_id = jsoned['user']['id']
        self.token = jsoned['user']['token']
        self.supported = []
        for filetype in jsoned['supported']:
             self.supported.append(filetype['extension'])

    def load_files(self, directory=None):
        """
        Load all files in the directory that match the supported extension list.

        directory defaults to present working directory.

        raises:
            ValueError if supported is not yet set.
        """
        if self.supported is None:
            raise ValueError('Supported not yet set - have you logged in yet?')

        if not directory:
            directory = os.getcwd()

        self.files = []
        for full_filename in glob.glob(os.path.join(directory, '*')):
            filename = os.path.basename(full_filename)
            # Skip hidden files.
            if filename.startswith('.'):
                continue

            # Make sure it's a supported extension.
            dummy, ext = os.path.splitext(full_filename)
            if ext in self.supported:
                self.files.append(full_filename)

            # Recurse into subdirectories.
            # XXX Symlinks may cause... issues.
            if os.path.isdir(full_filename):
                self.load_files(full_filename)

    def confirm(self):
        """
        Presents a dialog for the user to either list all files, or just upload.
        """
        print "Found %s files.  Press 'L' to list, or 'U' to start the " \
              "upload." % len(self.files)
        response = raw_input('--> ')

        print
        if response == 'L'.upper():
            print 'Listing found, supported files'
            for filename in self.files:
                print ' - ', filename
            print
            print "Press 'U' to start the upload if this looks reasonable."
            response = raw_input('--> ')
        if response == 'U'.upper():
            print 'Starting upload.'
            return True

        print 'Aborting'
        return False

    def __load_md5(self):
        """
        Reach out to iBroadcast and get an md5.
        """
        post_data = "user_id=%s&token=%s" % (self.user_id, self.token)

        # Send our request.
        response = requests.post(
            "https://sync.ibroadcast.com",
            data=post_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        if not response.ok:
            raise ServerError('Server returned bad status: ',
                             response.status_code)

        jsoned = response.json()

        self.md5 = jsoned['md5']
        
    def calcmd5(self, filePath="."):
        with open(filePath, 'rb') as fh:
            m = hashlib.md5()
            while True:
                data = fh.read(8192)
                if not data:
                    break
                m.update(data)
        return m.hexdigest() 

    def upload(self):
        """
        Go and perform an upload of any files that haven't yet been uploaded
        """
        self.__load_md5()

        for filename in self.files:

            print 'Uploading ', filename

            # Get an md5 of the file contents and compare it to whats up
            # there already
            file_md5 = self.calcmd5(filename)

            if file_md5 in self.md5:
                print 'Skipping - already uploaded.'
                continue
            upload_file = open(filename, 'rb')

            file_data = {
                'file': upload_file,
            }

            post_data = {
                'user_id': self.user_id,
                'token': self.token,
                'file_path' : filename,
                'method': self.CLIENT,
            }

            response = requests.post(
                "https://sync.ibroadcast.com",
                post_data,
                files=file_data,

            )

            upload_file.close()

            if not response.ok:
                raise ServerError('Server returned bad status: ',
                    response.status_code)
            jsoned = response.json()
            result = jsoned['result']

            if result is False:
                raise ValueError('File upload failed.')
        print 'Done'

if __name__ == '__main__':
    # NB: this could use parsearg
    if len(sys.argv) != 3:
        print "Usage: ibroadcast-uploader.py <username> <password>"
        sys.exit(1)
    uploader = Uploader(sys.argv[1], sys.argv[2])

    uploader.process()
