"""AI credentials live in Windows Credential Manager, never runtime settings."""

TARGET = 'DayLens/DeepSeek/API'


def read_key() -> str | None:
    try:
        import win32cred
        entry = win32cred.CredRead(TARGET, win32cred.CRED_TYPE_GENERIC, 0)
        blob = entry['CredentialBlob']
        return blob.decode('utf-16-le') if isinstance(blob, bytes) else str(blob)
    except Exception:
        return None


def save_key(key: str) -> None:
    key = key.strip()
    if not key or len(key) > 512 or any(ch.isspace() for ch in key):
        raise ValueError('请输入有效的API密钥')
    try:
        import win32cred
        win32cred.CredWrite({
            'Type': win32cred.CRED_TYPE_GENERIC, 'TargetName': TARGET,
            'UserName': 'DayLens', 'CredentialBlob': key.encode('utf-16-le'),
            'Persist': win32cred.CRED_PERSIST_LOCAL_MACHINE,
        }, 0)
    except Exception:
        raise RuntimeError('Windows凭据保存失败') from None


def delete_key() -> None:
    try:
        import win32cred
        win32cred.CredDelete(TARGET, win32cred.CRED_TYPE_GENERIC, 0)
    except Exception as exc:
        if getattr(exc, 'winerror', None) != 1168:
            raise RuntimeError('Windows凭据删除失败') from None
