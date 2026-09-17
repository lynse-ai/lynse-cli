"""Table formatting tests.

The ID column must never be truncated: downstream commands
(``meetings summary/transcript/outline/info``) copy the ID straight from the
``--table`` output, so a truncated ID silently breaks those lookups. Other
wide columns may be truncated, but must keep an explicit ``...`` marker.
"""

from lynse import _format_table


def test_format_table_keeps_full_long_id():
    items = [{
        "id": "1993855667662958593_1783500592708_7yq0h4qv",  # 42 chars
        "originalFilename": "短标题",
        "createTime": "2026-07-08 16:49:53",
    }]
    out = _format_table({"data": items}, "listFiles")
    # 完整 ID 必须出现在表格里，不能被 [:40] 截断
    assert "1993855667662958593_1783500592708_7yq0h4qv" in out


def test_format_table_truncates_wide_name_with_ellipsis():
    long_name = "x" * 100
    items = [{
        "id": "id1",
        "originalFilename": long_name,
        "createTime": "2026-07-08 16:49:53",
    }]
    out = _format_table({"data": items}, "listFiles")
    # 宽列应被截断并保留省略号标记，而不是静默丢信息
    assert "..." in out
    assert long_name not in out


def test_format_table_shows_duration_and_folder():
    items = [{
        "id": "id1",
        "originalFilename": "周会",
        "bizDuration": 5539,          # 92 分 19 秒
        "folderName": "🏗️产品研发",
        "createTime": "2026-09-02 14:19:55",
    }]
    out = _format_table({"data": items}, "listFiles")
    assert "Duration" in out
    assert "92:19" in out
    assert "Folder" in out
    assert "🏗️产品研发" in out


def test_format_table_duration_mmss_format():
    items = [
        {"id": "a", "originalFilename": "短", "bizDuration": 36},      # < 1 分钟
        {"id": "b", "originalFilename": "中", "bizDuration": 1539},    # 25:39
        {"id": "c", "originalFilename": "空", "bizDuration": None},    # 未解析/录制中
    ]
    out = _format_table({"data": items}, "listFiles")
    assert "0:36" in out
    assert "25:39" in out
    # None 时长按契约显示为空单元格，而不是 "None"
    assert "None" not in out


def test_format_table_null_folder_renders_empty():
    items = [{
        "id": "id1",
        "originalFilename": "未归类会议",
        "bizDuration": 60,
        "folderName": None,
        "folderId": None,
        "createTime": "2026-09-16 11:32:32",
    }]
    out = _format_table({"data": items}, "listFiles")
    data_row = [l for l in out.splitlines() if l.startswith("| id1")][0]
    # null 文件夹按契约为空单元格，而非 "None"
    assert "None" not in data_row
    assert "| Folder" in out
