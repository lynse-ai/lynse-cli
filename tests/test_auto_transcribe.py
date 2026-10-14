"""New recordings must not cause historical reruns or duplicate charged requests."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import lynse


def recording(file_id, **fields):
    return {'id': file_id, 'originalFilename': 'meeting.wav', 'contentType': 'audio/wav',
            'url': 'https://audio.example.test/meeting.wav', 'bizDuration': 60,
            'uploadStatus': 2, 'transcribeStatus': None, **fields}


class TranscriptionEndpointTests(unittest.TestCase):
    def setUp(self):
        self.api = lynse.LynseAPI.__new__(lynse.LynseAPI)
        self.api._request = Mock(return_value={'code': 200, 'data': {'taskId': 'task-1'}})

    def test_shared_contract_matches_cli_commands_and_api_methods(self):
        for method, operation in lynse.TRANSCRIPTION_OPERATIONS.items():
            self.assertTrue(callable(getattr(lynse.LynseAPI, method)))
            self.assertEqual(lynse._resolve_alias('meetings', [operation['subcommand']]),
                             (operation['command'], [], True))

    def test_submission_and_status_have_different_retry_rules(self):
        self.api.transcribe_file(' file-1 ', template_id='template-1',
                                 model_id='model-1', language_id='language-1')
        self.api._request.assert_called_once_with(
            'POST', '/api/business/file/trans', _retry_safe=False,
            json_data={'fileId': 'file-1', 'templateId': 'template-1',
                       'modelId': 'model-1', 'languageId': 'language-1'})
        self.api._request.reset_mock()
        self.api.get_transcription_status(['file-1', 'file-1', 'file-2'])
        self.api._request.assert_called_once_with(
            'POST', '/api/business/file/trans/status', _retry_safe=True,
            json_data={'fileIds': ['file-1', 'file-2']})

    def test_invalid_ids_never_reach_server(self):
        for value in ('', '  ', None, True, 'bad;id', 'bad..id'):
            with self.subTest(value=value), self.assertRaises(lynse.LynseAPIError):
                self.api.transcribe_file(value)
        for values in ([], None, [''], ['file'] * 101):
            with self.subTest(values=values), self.assertRaises(lynse.LynseAPIError):
                self.api.get_transcription_status(values)
        self.api._request.assert_not_called()


class AutoTranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'watch.json'
        self.files = [recording('old-1')]
        self.statuses = {}
        self.api = self.make_api()

    def make_api(self):
        api = lynse.LynseAPI.__new__(lynse.LynseAPI)
        api.api_host = 'https://api.example.test'
        api.get_current_customer = Mock(return_value={'code': 200, 'data': {'id': 'owner-1'}})
        api.page_files = Mock(side_effect=lambda page, size: {
            'code': 200, 'total': len(self.files),
            'data': self.files[(page - 1) * size:page * size]})
        api.get_file_info = Mock(side_effect=lambda file_id: {
            'code': 200, 'data': next(item for item in self.files if item['id'] == file_id)})
        api.get_transcription_status = Mock(side_effect=lambda ids: {
            'code': 200, 'data': {value: self.statuses.get(value) for value in ids}})
        api.transcribe_file = Mock(return_value={
            'code': 200, 'data': {'taskId': 'task-1', 'requiredPoints': 1}})
        return api

    def scan(self, **options):
        return self.api.auto_transcribe_new_recordings(state_file=str(self.path), **options)['data']

    def test_first_scan_baselines_every_page_without_transcribing(self):
        self.files[:] = [recording(f'old-{i}') for i in range(135)]
        result = self.scan()
        self.assertTrue(result['initialized'])
        self.assertEqual(result['baselineCount'], 135)
        self.assertEqual(self.api.page_files.call_count, 2)
        self.api.transcribe_file.assert_not_called()
        self.api.get_file_info.assert_not_called()

    def test_new_recording_submitted_once_across_restart(self):
        self.scan()
        self.files.append(recording('new-1'))
        result = self.scan(template_id='template-1')
        self.assertEqual(result['submitted'], [
            {'fileId': 'new-1', 'taskId': 'task-1', 'requiredPoints': 1}])
        self.api.transcribe_file.assert_called_once_with(
            'new-1', template_id='template-1', model_id=None, language_id=None)
        self.api = self.make_api()
        self.assertEqual(self.scan()['submitted'], [])
        self.api.transcribe_file.assert_not_called()

    def test_upload_in_progress_is_rechecked_after_it_finishes(self):
        self.scan()
        new = recording('new-1', uploadStatus=1)
        self.files.append(new)
        self.assertEqual(self.scan()['pending'], [
            {'fileId': 'new-1', 'reason': 'upload_not_complete'}])
        self.api.transcribe_file.assert_not_called()
        new['uploadStatus'] = 2
        self.assertEqual(len(self.scan()['submitted']), 1)

    def test_pipeline_started_elsewhere_and_non_audio_are_skipped(self):
        self.scan()
        self.files.extend([
            recording('running', transcribeStatus='RUNNING'),
            recording('complete', transcribeStatus='SUCCESS'),
            recording('failed', transcribeStatus='FAIL'),
            recording('task', transcribeTaskId='existing-task'),
            recording('remote'),
            recording('pdf', contentType='application/pdf'),
        ])
        self.statuses['remote'] = {'status': 'queued', 'taskId': 'remote-task'}
        self.assertEqual(len(self.scan()['skipped']), 6)
        self.api.transcribe_file.assert_not_called()

    def test_unknown_status_blocks_submission_until_resolved(self):
        self.scan()
        self.files.append(recording('new-1'))
        self.statuses['new-1'] = 'unrecognized'
        self.assertEqual(self.scan()['pending'][0]['reason'], 'unknown_transcription_status')
        self.api.transcribe_file.assert_not_called()
        self.statuses['new-1'] = 'not_started'
        self.assertEqual(len(self.scan()['submitted']), 1)

    def test_missing_status_metadata_blocks_submission(self):
        self.scan()
        new = recording('new-1')
        del new['transcribeStatus']
        self.files.append(new)
        self.assertEqual(self.scan()['pending'][0]['reason'], 'unknown_transcription_status')
        self.api.transcribe_file.assert_not_called()

    def test_network_failure_is_persisted_and_not_resubmitted(self):
        self.scan()
        self.files.append(recording('new-1'))
        self.api.transcribe_file.side_effect = lynse.LynseAPIError('network timeout')
        result = self.scan()
        self.assertEqual(result['needsReview'][0]['state'], 'needs_review')
        self.assertEqual(self.scan()['needsReview'][0]['error'], 'network timeout')
        self.api.transcribe_file.assert_called_once()

    def test_crash_after_attempt_marker_never_causes_retry(self):
        self.scan()
        self.files.append(recording('new-1'))
        self.api.transcribe_file.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.scan()
        self.api = self.make_api()
        self.assertEqual(self.scan()['needsReview'][0]['state'], 'submitting')
        self.api.transcribe_file.assert_not_called()

    def test_no_task_id_requires_review(self):
        self.scan()
        self.files.append(recording('new-1'))
        self.api.transcribe_file.return_value = {'code': 200, 'data': True}
        self.assertEqual(self.scan()['needsReview'][0]['state'], 'needs_review')
        self.scan()
        self.api.transcribe_file.assert_called_once()

    def test_ambiguous_submission_recovers_when_server_confirms_task(self):
        self.scan()
        new = recording('new-1')
        self.files.append(new)
        self.api.transcribe_file.side_effect = lynse.LynseAPIError('network timeout')
        self.scan()
        new.update(transcribeStatus='RUNNING', transcribeTaskId='accepted-task')
        result = self.scan()
        self.assertEqual(result['needsReview'], [])
        self.assertEqual(result['skipped'][0]['reason'], 'submission_confirmed')
        self.api.transcribe_file.assert_called_once()

    def test_failure_to_persist_attempt_blocks_charged_request(self):
        self.scan()
        self.files.append(recording('new-1'))
        save = lynse._save_auto_transcribe_state

        def fail_before_submit(path, state):
            if state['attempts']:
                raise OSError('disk full')
            save(path, state)

        with patch.object(lynse, '_save_auto_transcribe_state', side_effect=fail_before_submit):
            with self.assertRaises(OSError):
                self.scan()
        self.api.transcribe_file.assert_not_called()

    def test_corrupt_or_cross_account_state_is_not_reset(self):
        self.scan()
        original = self.path.read_text()
        self.api.get_current_customer.return_value = {'data': {'id': 'other-owner'}}
        with self.assertRaisesRegex(lynse.LynseAPIError, 'different account'):
            self.scan()
        self.assertEqual(self.path.read_text(), original)
        self.path.write_text('invalid json')
        with self.assertRaisesRegex(lynse.LynseAPIError, 'not reset'):
            self.scan()
        self.assertEqual(self.path.read_text(), 'invalid json')
        self.api.transcribe_file.assert_not_called()

    def test_default_state_is_scoped_to_token_verified_account_and_host(self):
        with patch.dict(lynse.os.environ, {'LYNSE_AUTO_TRANSCRIBE_STATE_DIR': ''}), \
                patch.object(lynse, '_get_user_config_dir', return_value=Path(self.temp.name)):
            first = self.api.auto_transcribe_new_recordings()['data']['stateFile']
            self.api.get_current_customer.return_value = {'data': {'id': 'owner-2'}}
            second = self.api.auto_transcribe_new_recordings()['data']['stateFile']
            self.api.api_host = 'https://other.example.test'
            third = self.api.auto_transcribe_new_recordings()['data']['stateFile']
        self.assertEqual(len({first, second, third}), 3)

    def test_administrator_can_set_persistent_state_directory(self):
        directory = Path(self.temp.name) / 'persistent'
        with patch.dict(lynse.os.environ, {'LYNSE_AUTO_TRANSCRIBE_STATE_DIR': str(directory)}):
            result = self.api.auto_transcribe_new_recordings()['data']
        self.assertEqual(Path(result['stateFile']).parent, directory.resolve())
        self.assertTrue(Path(result['stateFile']).exists())

    def test_concurrent_scan_is_rejected_before_submission(self):
        self.scan()
        self.files.append(recording('new-1'))
        with lynse._auto_transcribe_lock(self.path):
            with self.assertRaisesRegex(lynse.LynseAPIError, 'Another'):
                self.scan()
        self.api.transcribe_file.assert_not_called()

    def test_incomplete_or_repeated_inventory_does_not_create_baseline(self):
        for response in ({'data': None}, {'data': [], 'total': 10},
                         {'data': [{'id': 'one'}], 'total': 10}):
            self.api.page_files.side_effect = None
            self.api.page_files.return_value = response
            with self.subTest(response=response), self.assertRaises(lynse.LynseAPIError):
                self.scan()
            self.assertFalse(self.path.exists())


class AutoTranscriptionCLITests(unittest.TestCase):
    def test_main_dispatches_single_scan_without_sleeping(self):
        api = Mock()
        api.auto_transcribe_new_recordings.return_value = {'code': 200, 'data': {
            'initialized': True, 'baselineCount': 1, 'submitted': [], 'needsReview': []}}
        with patch.object(lynse.sys, 'argv', ['lynse', 'meetings', 'auto-transcribe',
                                           '--once', '--json', '--state-file', '/tmp/watch.json']), \
                patch.object(lynse, 'LynseAPI', return_value=api), \
                patch.object(lynse, '_maybe_print_update_notice'), \
                patch.object(lynse.time, 'sleep') as sleep, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            lynse.main()
        api.auto_transcribe_new_recordings.assert_called_once_with(state_file='/tmp/watch.json')
        self.assertTrue(json.loads(output.getvalue())['data']['initialized'])
        sleep.assert_not_called()

    def test_review_required_exits_nonzero(self):
        api = Mock()
        api.auto_transcribe_new_recordings.return_value = {'code': 200, 'data': {
            'needsReview': [{'fileId': 'file-1', 'state': 'submitting'}]}}
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as error:
            lynse._handle_auto_transcribe(api, ['--once'], {'format': 'json', 'output_file': None})
        self.assertEqual(error.exception.code, lynse.EXIT_SERVER)

    def test_invalid_arguments_do_not_submit(self):
        for args in (['--interval', '1'], ['--interval', 'abc'], ['--state-file'],
                     ['--typo'], ['--template', '--once']):
            api = Mock()
            with self.subTest(args=args), self.assertRaises(lynse.LynseAPIError):
                lynse._handle_auto_transcribe(api, args, {'output_file': None})
            api.auto_transcribe_new_recordings.assert_not_called()
        with self.assertRaises(lynse.LynseAPIError):
            lynse._handle_auto_transcribe(Mock(), [], {'output_file': 'result.json'})


if __name__ == '__main__':
    unittest.main()
