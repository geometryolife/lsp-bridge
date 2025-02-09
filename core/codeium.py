#! /usr/bin/env python
# -*- coding: utf-8 -*-

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json
import os
import re
import subprocess
import tempfile
import time
import traceback
import urllib.parse
import urllib.request

from core.utils import *

CODEIUM_EXECUTABLE = 'language_server.exe' if get_os_name() == 'windows' else 'language_server'

class Codeium:
    def __init__(self):
        self.is_run = False
        self.is_get_info = False

        self.server_port = ''

    def complete(self, cursor_offset, editor_language, tab_size, text, insert_spaces, language):
        self.get_info()
        self.run_local_server()

        data = {
            'metadata': self.metadata,
            'document': {
                'cursor_offset': cursor_offset,
                'editor_language': editor_language,
                'text': text,
                'language': language
            },
            'editor_options': {
                'insert_spaces': insert_spaces,
                'tab_size': tab_size
            }
        }

        self.dispatch(self.post_request(self.make_url('GetCompletions'), data))

    def accept(self, id):
        data = {
            'metadata': self.metadata,
            'completion_id': id
        }

        self.post_request(self.make_url('AcceptCompletion'), data)

    def auth(self):
        import uuid

        params = {
            'response_type': 'token',
            'redirect_uri': 'vim-show-auth-token',
            'state': str(uuid.uuid4()),
            'scope': 'openid profile email',
            'redirect_parameters_type': 'query'
        }

        url = 'https://codeium.com/profile?' + urllib.parse.urlencode(params)

        eval_in_emacs('browse-url', url)

    def get_api_key(self, auth_token):
        message_emacs('Getting api key...')

        api_key = self.post_request('https://api.codeium.com/register_user/', {'firebase_id_token': auth_token})['api_key']

        eval_in_emacs('customize-save-variable', "'acm-backend-codeium-api-key", api_key)

        message_emacs('Done.')

        self.is_get_info = False
        self.get_info()

    def dispatch(self, data):
        completion_candidates = []

        current_line = get_current_line()

        if 'completionItems' in data:
            for completion in data['completionItems'][:self.max_num_results - 1]:
                label = completion['completion']['text']
                display_label = label
                completionParts = completion.get('completionParts', [{}])[0]

                if label == current_line:
                    continue

                if 'type' in completionParts and completionParts['type'] == 'COMPLETION_PART_TYPE_BLOCK':
                    display_label = completionParts['text']

                candidate = {
                    'key': label,
                    'icon': 'codeium',
                    'label': label,
                    'display-label': display_label.split('\n')[0].strip(),
                    'annotation': 'Codeium',
                    'backend': 'codeium',
                    'id': completion['completion']['completionId']
                }

                completion_candidates.append(candidate)

        eval_in_emacs('lsp-bridge-search-backend--record-items', 'codeium', completion_candidates)

    def make_url(self, api):
        return f'http://localhost:{self.server_port}/exa.language_server_pb.LanguageServerService/{api}'

    def run_local_server(self):
        if self.is_run:
            return

        try:
            self.is_run = True

            message_emacs('Waiting for Codeium local server to start...')

            self.manager_dir = tempfile.mkdtemp(prefix="codeium_")

            process = subprocess.Popen([self.path,
                                        '--api_server_host', self.api_server_host,
                                        '--api_server_port', str(self.api_server_port),
                                        '--manager_dir', self.manager_dir])

            self.get_server_port()
        except:
            self.is_run = False

            process.kill()

            logger.error(traceback.format_exc())
            message_emacs('Cannot start codeium local server.')

    def get_info(self):
        if self.is_get_info:
            return

        [API_KEY,
         self.api_server_host,
         self.api_server_port,
         self.folder,
         VERSION,
         self.max_num_results,
         EMACS_VERSION] = get_emacs_vars(['acm-backend-codeium-api-key',
                                          'acm-backend-codeium-api-server-host',
                                          'acm-backend-codeium-api-server-port',
                                          'codeium-bridge-folder',
                                          'codeium-bridge-binary-version',
                                          'acm-backend-codeium-candidates-number',
                                          'emacs-version'])

        self.metadata = {
            'api_key': API_KEY,
            'extension_version': VERSION,
            'ide_name': 'emacs',
            'ide_version': EMACS_VERSION
        }
        self.path = os.path.join(self.folder, CODEIUM_EXECUTABLE)

    def get_server_port(self):
        pattern = re.compile('\\d{5}')

        while True:
            try:
                files = [f for f in os.listdir(self.manager_dir) if pattern.match(f)]

                time.sleep(0.1)

                if len(files) == 0:
                    continue
                else:
                    break
            except:
                pass

        if len(files) > 0:
            self.server_port = files[0]
        else:
            time.sleep(0.1)
            self.get_server_port()

    def post_request(self, url, data):
        json_data = json.dumps(data).encode('utf-8')

        req = urllib.request.Request(url=url, method='POST')
        req.data = json_data
        req.add_header('Content-Type', 'application/json')
        req.add_header('Content-Length', len(json_data))

        try:
            with urllib.request.urlopen(req) as response:
                response_data = response.read().decode('utf-8')
                return json.loads(response_data)
        except:
            return {}
