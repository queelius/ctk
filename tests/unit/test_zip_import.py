import json
import zipfile
from pathlib import Path

from ctk.cli import _read_zip_export

CLAUDE_CONVS = [
    {
        "uuid": "z1",
        "name": "Zipped",
        "created_at": "2026-06-09T00:00:00Z",
        "updated_at": "2026-06-09T00:00:00Z",
        "chat_messages": [
            {
                "uuid": "m1",
                "sender": "human",
                "text": "hi",
                "created_at": "2026-06-09T00:00:01Z",
            }
        ],
    }
]


def _make_zip(path: Path, members: dict) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, payload in members.items():
            zf.writestr(name, payload)
    return path


def test_claude_zip_reads_json_in_memory_no_media_dir(tmp_path):
    zp = _make_zip(
        tmp_path / "claude.zip",
        {
            "conversations.json": json.dumps(CLAUDE_CONVS),
            "users.json": "[]",
            "memories.json": "{}",
        },
    )
    data, media_dir = _read_zip_export(zp)
    assert json.loads(data)[0]["uuid"] == "z1"
    assert media_dir is None  # nothing extracted for media-free archives


def test_chatgpt_style_zip_extracts_only_media(tmp_path):
    zp = _make_zip(
        tmp_path / "oai.zip",
        {
            "conversations.json": json.dumps([{"title": "t", "mapping": {}}]),
            "dalle-generations/img.webp": "fakebytes",
        },
    )
    data, media_dir = _read_zip_export(zp)
    assert "mapping" in data
    assert media_dir is not None
    assert (Path(media_dir) / "dalle-generations" / "img.webp").exists()
    assert not (Path(media_dir) / "conversations.json").exists()


def test_zip_traversal_members_are_skipped(tmp_path):
    zp = _make_zip(
        tmp_path / "evil.zip",
        {
            "conversations.json": json.dumps(CLAUDE_CONVS),
            "../evil.bin": "x",
            "/abs/evil.bin": "x",
        },
    )
    data, media_dir = _read_zip_export(zp)
    assert json.loads(data)[0]["uuid"] == "z1"
    if media_dir is not None:
        extracted = [str(p) for p in Path(media_dir).rglob("*")]
        assert not any("evil" in p for p in extracted)
    assert not (tmp_path / "evil.bin").exists()


def test_zip_in_single_top_level_directory(tmp_path):
    zp = _make_zip(
        tmp_path / "nested.zip",
        {
            "export-2026/conversations.json": json.dumps(CLAUDE_CONVS),
        },
    )
    data, _ = _read_zip_export(zp)
    assert json.loads(data)[0]["uuid"] == "z1"
