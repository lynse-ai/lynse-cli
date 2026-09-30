"""Offline checks for the Todo API surface: insert / count / range / offline / batch update."""

import unittest

import lynse


class _Capture:
    """Stub _request: record (method, path, kwargs) and return a canned response."""

    def __init__(self, response=None):
        self.calls = []
        self.response = response or {'code': 200, 'msg': '操作成功', 'data': True}

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return dict(self.response)


def make_api(capture=None):
    api = lynse.LynseAPI.__new__(lynse.LynseAPI)
    capture = capture or _Capture()
    api._request = capture
    return api, capture


class InsertTodosTests(unittest.TestCase):
    def test_builds_normalized_request_body(self):
        capture = _Capture()
        api, capture = make_api(capture)
        api.insert_todos([
            {'todoContent': ' 跟进合同 ', 'fileId': 'f-1',
             'expectedCompleteTime': '2026-10-08 18:00:00',
             'displayWeight': '3', 'owner': 'Ann', 'syncStatus': '0'},
            '纯文本待办',
        ])
        method, path, kwargs = capture.calls[0]
        self.assertEqual(method, 'POST')
        self.assertEqual(path, '/api/business/file/todo/insert')
        self.assertEqual(kwargs['json_data'], {'todoInsertList': [
            {'todoContent': '跟进合同', 'fileId': 'f-1',
             'expectedCompleteTime': '2026-10-08 18:00:00',
             'displayWeight': 3, 'owner': 'Ann', 'syncStatus': 0},
            {'todoContent': '纯文本待办'},
        ]})

    def test_rejects_empty_over_limit_blank_content_and_bad_fields(self):
        api, _ = make_api()
        with self.assertRaisesRegex(lynse.LynseAPIError, '不能为空'):
            api.insert_todos([])
        with self.assertRaisesRegex(lynse.LynseAPIError, '最多100条'):
            api.insert_todos([{'todoContent': f't{i}'} for i in range(101)])
        with self.assertRaisesRegex(lynse.LynseAPIError, 'todoContent'):
            api.insert_todos(['   '])
        with self.assertRaisesRegex(lynse.LynseAPIError, 'yyyy-MM-dd HH:mm:ss'):
            api.insert_todos([{'todoContent': 'x', 'expectedCompleteTime': '2026-10-08'}])
        with self.assertRaisesRegex(lynse.LynseAPIError, 'syncStatus'):
            api.insert_todos([{'todoContent': 'x', 'syncStatus': 2}])
        with self.assertRaisesRegex(lynse.LynseAPIError, 'displayWeight'):
            api.insert_todos([{'todoContent': 'x', 'displayWeight': 'high'}])


class CountAndListTests(unittest.TestCase):
    def test_count_uses_get_endpoint(self):
        capture = _Capture({'code': 200, 'data': {'nearWeekCount': 1}})
        api, _ = make_api(capture)
        result = api.count_todos()
        method, path, _ = capture.calls[0]
        self.assertEqual(method, 'GET')
        self.assertEqual(path, '/api/business/file/todo/count')
        self.assertEqual(result['data']['nearWeekCount'], 1)

    def test_range_query_expands_dates_and_pagination(self):
        capture = _Capture({'code': 200, 'data': []})
        api, _ = make_api(capture)
        api.list_todos_by_range(is_completed='0', start_time='2026-09-01',
                                end_time='2026-09-30', page_num='2', page_size='500')
        method, path, kwargs = capture.calls[0]
        self.assertEqual((method, path), ('POST', '/api/business/file/todo/list'))
        self.assertEqual(kwargs['json_data'], {
            'isCompleted': 0,
            'startTime': '2026-09-01 00:00:00',
            # endTime 为开区间：日期型结尾补到次日 0 点
            'endTime': '2026-10-01 00:00:00',
            'pageNum': 2,
            'pageSize': 100,
        })

    def test_range_query_omits_absent_filters_and_rejects_bad_status(self):
        capture = _Capture({'code': 200, 'data': []})
        api, _ = make_api(capture)
        api.list_todos_by_range()
        _, _, kwargs = capture.calls[0]
        self.assertEqual(kwargs['json_data'], {})
        with self.assertRaisesRegex(lynse.LynseAPIError, 'isCompleted'):
            api.list_todos_by_range(is_completed=2)
        with self.assertRaisesRegex(lynse.LynseAPIError, 'yyyy-MM-dd HH:mm:ss'):
            api.list_todos_by_range(start_time='09/01/2026')

    def test_range_query_accepts_full_timestamps_verbatim(self):
        capture = _Capture({'code': 200, 'data': []})
        api, _ = make_api(capture)
        api.list_todos_by_range(start_time='2026-09-01 08:30:00',
                                end_time='2026-09-01 12:00:00')
        _, _, kwargs = capture.calls[0]
        self.assertEqual(kwargs['json_data']['startTime'], '2026-09-01 08:30:00')
        self.assertEqual(kwargs['json_data']['endTime'], '2026-09-01 12:00:00')

    def test_offline_list_posts_empty_body(self):
        capture = _Capture()
        api, _ = make_api(capture)
        api.list_offline_todos()
        method, path, kwargs = capture.calls[0]
        self.assertEqual((method, path), ('POST', '/api/business/file/todo/offline/list'))
        self.assertEqual(kwargs['json_data'], {})


class UpdateTodosTests(unittest.TestCase):
    def test_single_reschedule_keeps_legacy_shape(self):
        capture = _Capture()
        api, _ = make_api(capture)
        api.reschedule_todo(' todo-1 ', '2026-10-08 09:00:00')
        method, path, kwargs = capture.calls[0]
        self.assertEqual((method, path), ('POST', '/api/business/file/todo/update'))
        self.assertEqual(kwargs['json_data'], {'todoUpdateList': [
            {'todoId': 'todo-1', 'expectedCompleteTime': '2026-10-08 09:00:00'},
        ]})

    def test_empty_deadline_sends_explicit_null_to_clear(self):
        capture = _Capture()
        api, _ = make_api(capture)
        api.reschedule_todo('todo-1', '')
        _, _, kwargs = capture.calls[0]
        self.assertEqual(kwargs['json_data'], {'todoUpdateList': [
            {'todoId': 'todo-1', 'expectedCompleteTime': None},
        ]})

    def test_batch_update_normalizes_and_sanitizes_ids(self):
        capture = _Capture()
        api, _ = make_api(capture)
        api.reschedule_todo([
            {'todoId': ' t-1 ', 'isCompleted': '1', 'todoContent': '新内容'},
            {'todoId': 't-2', 'displayWeight': 5, 'owner': 'Bo',
             'expectedCompleteTime': None},
        ])
        _, _, kwargs = capture.calls[0]
        self.assertEqual(kwargs['json_data'], {'todoUpdateList': [
            {'todoId': 't-1', 'isCompleted': 1, 'todoContent': '新内容'},
            {'todoId': 't-2', 'displayWeight': 5, 'owner': 'Bo',
             'expectedCompleteTime': None},
        ]})

    def test_update_todos_rejects_duplicates_and_bad_values(self):
        api, _ = make_api()
        with self.assertRaisesRegex(lynse.LynseAPIError, 'duplicate'):
            api.update_todos([{'todoId': 'a'}, {'todoId': 'a'}])
        with self.assertRaisesRegex(lynse.LynseAPIError, 'isCompleted'):
            api.update_todos([{'todoId': 'a', 'isCompleted': 3}])
        with self.assertRaisesRegex(lynse.LynseAPIError, 'todoId'):
            api.update_todos([{'todoContent': 'no id'}])
        with self.assertRaisesRegex(lynse.LynseAPIError, 'yyyy-MM-dd HH:mm:ss'):
            api.update_todos([{'todoId': 'a', 'expectedCompleteTime': '明天'}])

    def test_missing_todo_id_fails_fast(self):
        api, _ = make_api()
        with self.assertRaisesRegex(lynse.LynseAPIError, 'todoId'):
            api.reschedule_todo('', '2026-10-08 09:00:00')


class _FakeTodoAPI:
    """Captures calls made by the CLI arg handlers."""

    def __init__(self):
        self.insert_items = None
        self.range_kwargs = None
        self.reschedule_args = None

    def insert_todos(self, items):
        self.insert_items = items
        return {'code': 200, 'msg': '操作成功', 'data': True}

    def list_todos_by_range(self, **kwargs):
        self.range_kwargs = kwargs
        return {'code': 200, 'msg': 'SUCCESS', 'data': []}

    def reschedule_todo(self, *args):
        self.reschedule_args = args
        return {'code': 200, 'msg': '操作成功', 'data': True}


class CliHandlerTests(unittest.TestCase):
    def test_add_single_with_flags(self):
        fake = _FakeTodoAPI()
        lynse._handle_insert_todos(fake, ['买牛奶', '--file', 'f9',
                                          '--deadline', '2026-10-01 08:00:00',
                                          '--owner', 'Ann', '--sync', '0'])
        self.assertEqual(fake.insert_items, [{'fileId': 'f9',
                                              'expectedCompleteTime': '2026-10-01 08:00:00',
                                              'owner': 'Ann', 'syncStatus': '0',
                                              'todoContent': '买牛奶'}])

    def test_add_multiple_via_content_flags(self):
        fake = _FakeTodoAPI()
        lynse._handle_insert_todos(fake, ['--content', 'a', '--content', 'b'])
        self.assertEqual(fake.insert_items,
                         [{'todoContent': 'a'}, {'todoContent': 'b'}])

    def test_add_json_array_passes_through(self):
        fake = _FakeTodoAPI()
        payload = [{'todoContent': 'x'}, {'todoContent': 'y', 'fileId': 'f1'}]
        lynse._handle_insert_todos(fake, [str(payload).replace("'", '"')])
        self.assertEqual(fake.insert_items, payload)

    def test_range_handler_parses_flags_and_dates(self):
        fake = _FakeTodoAPI()
        lynse._handle_todos_range(fake, ['2026-09-01', '2026-09-30',
                                         '--status', '1', '--page', '2', '--size', '10'])
        self.assertEqual(fake.range_kwargs, {
            'start_time': '2026-09-01 00:00:00',
            'end_time': '2026-10-01 00:00:00',
            'is_completed': '1', 'page_num': '2', 'page_size': '10',
        })

    def test_reschedule_handler_accepts_pair_and_json_batch(self):
        fake = _FakeTodoAPI()
        lynse._handle_reschedule_todo(fake, ['id-1', '2026-10-08 09:00:00'])
        self.assertEqual(fake.reschedule_args, ('id-1', '2026-10-08 09:00:00'))
        batch = [{'todoId': 'a', 'isCompleted': 1}]
        lynse._handle_reschedule_todo(fake, [str(batch).replace("'", '"')])
        self.assertEqual(fake.reschedule_args, (batch,))

    def test_subcommand_aliases_resolve(self):
        for sub, expected in (('add', 'insertTodos'), ('count', 'countTodos'),
                              ('range', 'listTodosByRange'),
                              ('offline', 'listOfflineTodos'),
                              ('update', 'rescheduleTodo')):
            command, args, _ = lynse._resolve_alias('todos', [sub, 'x'])
            self.assertEqual((command, args), (expected, ['x']))


class FormattingTests(unittest.TestCase):
    def test_count_text_lists_five_buckets(self):
        text = lynse._format_text({'data': {'nearWeekCount': 2, 'expiredCount': 1}},
                                   'countTodos')
        self.assertIn('Due this week: 2', text)
        self.assertIn('Expired: 1', text)
        self.assertIn('No deadline: 0', text)

    def test_insert_text_and_list_tables(self):
        self.assertEqual(lynse._format_text({'code': 200, 'data': True}, 'insertTodos'),
                         'Todos inserted.')
        offline = lynse._format_table({'data': [
            {'isCompleted': 1, 'todoContent': 'x', 'owner': 'Ann', 'syncStatus': 1}
        ]}, 'listOfflineTodos')
        self.assertIn('Owner', offline)
        self.assertIn('Sync', offline)
        ranged = lynse._format_table({'data': [
            {'isCompleted': 0, 'todoContent': 'y', 'expectedCompleteTime': '2026-10-01 08:00:00'}
        ]}, 'listTodosByRange')
        self.assertIn('Deadline', ranged)
        self.assertIn('2026-10-01 08:00:00', ranged)

    def test_range_text_renders_checkmarks(self):
        text = lynse._format_text({'data': [
            {'isCompleted': 1, 'todoContent': 'done one'},
            {'isCompleted': 0, 'todoContent': 'open one'},
        ]}, 'listTodosByRange')
        self.assertIn('✓ done one', text)
        self.assertIn('○ open one', text)


if __name__ == '__main__':
    unittest.main()
