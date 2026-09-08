import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from daylens.services import intelligence_credentials as credentials


def test_save_passes_unicode_to_windows(monkeypatch):
    entries = []

    def write(entry, flags):
        assert isinstance(entry['CredentialBlob'], str)
        entries.append(entry)

    monkeypatch.setitem(sys.modules, 'win32cred', SimpleNamespace(
        CRED_TYPE_GENERIC=1, CRED_PERSIST_LOCAL_MACHINE=2, CredWrite=write))
    credentials.save_key(' diagnostic-only ')
    assert entries[0]['CredentialBlob'] == 'diagnostic-only'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows credentials required')
def test_windows_roundtrip_uses_isolated_temporary_target(monkeypatch):
    pytest.importorskip('win32cred')
    monkeypatch.setattr(credentials, 'TARGET', 'DayLens/Diagnostics/' + str(uuid4()))
    try:
        credentials.save_key('diagnostic-only')
        assert credentials.read_key() == 'diagnostic-only'
        credentials.delete_key()
        assert credentials.read_key() is None
    finally:
        credentials.delete_key()
