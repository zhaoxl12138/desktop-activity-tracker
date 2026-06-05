from __future__ import annotations

from types import SimpleNamespace

from daylens.console import configure_console_encoding


class _FakeStream:
    def __init__(self, encoding: str | None):
        self.encoding = encoding
        self.calls: list[tuple[str, str]] = []

    def reconfigure(self, *, encoding: str, errors: str) -> None:
        self.calls.append((encoding, errors))
        self.encoding = encoding


def test_configure_console_encoding_reconfigures_non_utf8_streams():
    stdout = _FakeStream("cp936")
    stderr = _FakeStream("gbk")
    streams = SimpleNamespace(stdout=stdout, stderr=stderr)

    configure_console_encoding(streams)

    assert stdout.calls == [("utf-8", "replace")]
    assert stderr.calls == [("utf-8", "replace")]


def test_configure_console_encoding_skips_utf8_streams():
    stdout = _FakeStream("UTF-8")
    stderr = _FakeStream("utf-8")
    streams = SimpleNamespace(stdout=stdout, stderr=stderr)

    configure_console_encoding(streams)

    assert stdout.calls == []
    assert stderr.calls == []
