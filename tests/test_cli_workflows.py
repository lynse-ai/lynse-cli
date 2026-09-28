"""Offline checks for first use, account boundaries, and readable recordings."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import lynse


TOKEN = 'aaaa.bbbb.cccc'


class LoginWorkflowTests(unittest.TestCase):
    def test_public_host_is_default_and_test_host_requires_override(self):
        self.assertEqual(lynse.DEFAULT_API_HOST, 'https://api.lynse.cn')
        with patch.dict(os.environ, {}, clear=True), patch.object(lynse, '_load_install_env'):
            production = lynse.LynseAPI(api_key='dk_test')
            test = lynse.LynseAPI(api_key='dk_test', api_host='https://gapp.lynse.cn')
        self.assertEqual(production.api_host, 'https://api.lynse.cn')
        self.assertEqual(test.api_host, 'https://gapp.lynse.cn')

    def test_missing_key_is_an_auth_failure(self):
        error = lynse.LynseAPIError('LYNSE_API_KEY is not configured.')
        self.assertEqual(lynse._resolve_exit_code(error), lynse.EXIT_AUTH)

    def test_fresh_login_uses_official_host_and_logs_out_locally(self):
        with tempfile.TemporaryDirectory() as temp:
            config_dir = Path(temp)
            response = SimpleNamespace(
                status_code=200,
                json=lambda: {'data': {'accessToken': TOKEN}},
            )
            with patch.dict(os.environ, {}, clear=True), \
                    patch.object(lynse, '_get_user_config_dir', return_value=config_dir), \
                    patch.object(lynse, '_load_install_env'), \
                    patch.object(lynse.requests, 'post', return_value=response) as post, \
                    contextlib.redirect_stdout(io.StringIO()):
                lynse._handle_auth_command('__auth_login__', ['--api-key', 'dk_test'], {'format': 'json'})
                config = json.loads((config_dir / 'config.json').read_text())
                self.assertEqual(config['api_key'], 'dk_test')
                self.assertNotIn('access_token', config)
                self.assertEqual((config_dir / 'tokens.json').read_text(), TOKEN)
                self.assertEqual(post.call_args.args[0], lynse.DEFAULT_API_HOST + '/api/auth/apikey/token')

                lynse._handle_auth_command('__auth_logout__', ['--tokens-only'], {'format': 'json'})
                self.assertEqual(json.loads((config_dir / 'config.json').read_text())['api_key'], 'dk_test')
                lynse._handle_auth_command('__auth_logout__', [], {'format': 'json'})
                self.assertNotIn('api_key', json.loads((config_dir / 'config.json').read_text()))
                self.assertFalse((config_dir / 'tokens.json').exists())

    def test_plain_http_host_is_rejected_before_credentials_are_sent(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(lynse, '_load_install_env'):
            with self.assertRaisesRegex(lynse.LynseAPIError, 'HTTPS'):
                lynse.LynseAPI(api_host='http://example.test', api_key='dk_test')


class OwnerBoundaryTests(unittest.TestCase):
    def make_api(self, owner_response):
        http = SimpleNamespace(
            get=lambda *a, **k: owner_response,
            request=lambda *a, **k: SimpleNamespace(
                status_code=200, text='{}', json=lambda: {'code': 200, 'data': []}
            ),
        )
        with patch.dict(os.environ, {}, clear=True), patch.object(lynse, '_load_install_env'):
            api = lynse.LynseAPI(api_key='', access_token=TOKEN, owner_id='owner-1', http_client=http)
        return api, http

    def test_matching_owner_allows_business_request(self):
        owner_response = SimpleNamespace(
            status_code=200, json=lambda: {'code': 200, 'data': {'id': 'owner-1'}}
        )
        api, http = self.make_api(owner_response)
        calls = []
        http.request = lambda *a, **k: calls.append(a) or SimpleNamespace(
            status_code=200, text='{}', json=lambda: {'code': 200, 'data': []}
        )
        api._request('GET', '/api/business/file/list')
        self.assertEqual(len(calls), 1)

    def test_mismatch_or_unavailable_owner_blocks_business_request(self):
        for response in (
            SimpleNamespace(status_code=200, json=lambda: {'code': 200, 'data': {'id': 'other'}}),
            SimpleNamespace(status_code=503, json=lambda: {}),
        ):
            api, http = self.make_api(response)
            http.request = lambda *a, **k: self.fail('business request crossed owner boundary')
            with self.assertRaises(lynse.LynseAPIError):
                api._request('GET', '/api/business/file/list')

    def test_expired_token_is_refreshed_before_owner_checked_request(self):
        responses = iter([
            SimpleNamespace(status_code=401, json=lambda: {}),
            SimpleNamespace(status_code=200, json=lambda: {'code': 200, 'data': {'id': 'owner-1'}}),
        ])
        api, http = self.make_api(None)
        api.api_key = 'dk_test'
        http.get = lambda *a, **k: next(responses)
        used_headers = []
        http.request = lambda *a, **k: used_headers.append(k['headers']) or SimpleNamespace(
            status_code=200, text='{}', json=lambda: {'code': 200, 'data': []}
        )
        api._get_token = lambda refresh=False: 'new.token.value' if refresh else TOKEN
        api._request('GET', '/api/business/file/list')
        self.assertEqual(used_headers[0]['Authorization'], 'new.token.value')


class RecordingOutputTests(unittest.TestCase):
    def test_summary_and_transcript_text_are_directly_readable(self):
        summary = lynse._format_text({'data': {'content': '# Decisions\n- Ship'}}, 'getConclusion')
        transcript = lynse._format_text({
            'data': {'records': [{'beginTime': 1200, 'speakerName': 'Alice', 'text': 'Hello'}]}
        }, 'getTranscriptionRecord')
        self.assertEqual(summary, '# Decisions\n- Ship')
        self.assertEqual(transcript, '[00:01.200] Alice: Hello')

    def test_paginated_search_results_are_visible_in_text_and_table(self):
        response = {'code': 200, 'data': {'records': [
            {'id': 'file-1', 'originalFilename': 'Roadmap', 'createTime': '2026-09-10'}
        ], 'total': 12}}
        self.assertIn('Showing 1 of 12', lynse._format_text(response, 'searchFiles'))
        self.assertIn('file-1', lynse._format_table(response, 'searchFiles'))

    def test_terminal_defaults_to_text_and_pipe_to_json(self):
        with patch.object(lynse.sys, 'stdout', SimpleNamespace(isatty=lambda: True)):
            flags, _ = lynse._parse_global_flags(['meetings', 'summary', 'file-1'])
            self.assertEqual(flags['format'], 'text')
        with patch.object(lynse.sys, 'stdout', SimpleNamespace(isatty=lambda: False)):
            flags, _ = lynse._parse_global_flags(['meetings', 'summary', 'file-1'])
            self.assertEqual(flags['format'], 'json')

    def test_date_filtered_search_keeps_pagination(self):
        api = lynse.LynseAPI.__new__(lynse.LynseAPI)
        api._sanitize_param = lambda value, _kind: value
        records = [
            {'id': f'id-{i}', 'recordStartTime': '2026-09-10' if i < 15 else '2026-08-10'}
            for i in range(105)
        ]
        calls = []

        def request(method, path, params):
            calls.append(params['pageNum'])
            start = (params['pageNum'] - 1) * 100
            return {'code': 200, 'total': len(records), 'data': records[start:start + 100]}

        api._request = request
        result = api.search_files('Roadmap', page=2, page_size=5,
                                  from_date='2026-09-01', to_date='2026-09-30')
        self.assertEqual(calls, [1, 2])
        self.assertEqual(result['total'], 15)
        self.assertEqual([row['id'] for row in result['data']], [f'id-{i}' for i in range(5, 10)])

    def test_summary_output_file_contains_markdown_by_default(self):
        class FakeAPI:
            def get_conclusion(self, _file_id, first_only=True):
                return {'code': 200, 'data': {'content': '# Decisions\n- Ship'}}

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'summary.md'
            with patch.object(lynse.sys, 'argv', ['lynse', 'meetings', 'summary', 'file-1', '-o', str(output)]), \
                    patch.object(lynse, 'LynseAPI', return_value=FakeAPI()), \
                    patch.object(lynse, '_maybe_print_update_notice'), \
                    contextlib.redirect_stderr(io.StringIO()):
                lynse.main()
            self.assertEqual(output.read_text(), '# Decisions\n- Ship\n')
            if os.name != 'nt':
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
