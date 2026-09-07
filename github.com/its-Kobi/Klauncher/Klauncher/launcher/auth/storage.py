from __future__ import annotations
import json, os, base64
from pathlib import Path
from typing import Optional, List, Dict
from launcher import paths

# Secure storage: prefer Windows DPAPI via win32crypt, else keyring, else restricted file
try:
    import win32crypt  # type: ignore
    HAS_DPAPI = True
except ImportError:
    HAS_DPAPI = False

try:
    import keyring  # type: ignore
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

SERVICE_NAME = "KLauncher-Microsoft"

def _dpapi_encrypt(data: bytes) -> bytes:
    if HAS_DPAPI:
        return win32crypt.CryptProtectData(data, None, None, None, None, 0)
    return data

def _dpapi_decrypt(data: bytes) -> bytes:
    if HAS_DPAPI:
        try:
            _, dec = win32crypt.CryptUnprotectData(data, None, None, None, 0)
            return dec
        except Exception:
            return data
    return data

def _accounts_path() -> Path:
    return paths.get_data_dir() / "microsoft_accounts.json"

def _secure_path() -> Path:
    return paths.get_data_dir() / "microsoft_tokens.dat"

def save_accounts(accounts: List[Dict]):
    # accounts contain non-sensitive display data (uuid, username, expires_at)
    # Sensitive tokens are stored separately via DPAPI/keyring
    p = _accounts_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Only save display fields, not tokens in plain
    safe = []
    for acc in accounts:
        safe.append({
            "uuid": acc.get("uuid"),
            "username": acc.get("username"),
            "xuid": acc.get("xuid"),
            "expires_at": acc.get("expires_at"),
        })
    with open(p, "w", encoding="utf-8") as f:
        json.dump(safe, f, indent=2)
    # Restrict permissions on Windows not needed, but try chmod 0o600 on posix
    try:
        os.chmod(p, 0o600)
    except:
        pass

def load_accounts_meta() -> List[Dict]:
    p = _accounts_path()
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def _store_token(key: str, token: str):
    if HAS_KEYRING:
        try:
            keyring.set_password(SERVICE_NAME, key, token)
            return
        except:
            pass
    # Fallback DPAPI file
    # Store as base64 encrypted blob in a json dict
    sec_path = _secure_path()
    data = {}
    if sec_path.exists():
        try:
            with open(sec_path, "rb") as f:
                raw = f.read()
                if HAS_DPAPI:
                    raw = _dpapi_decrypt(raw)
                data = json.loads(raw.decode("utf-8"))
        except:
            data = {}
    data[key] = token
    raw = json.dumps(data).encode("utf-8")
    if HAS_DPAPI:
        raw = _dpapi_encrypt(raw)
    sec_path.parent.mkdir(parents=True, exist_ok=True)
    with open(sec_path, "wb") as f:
        f.write(raw)
    try:
        os.chmod(sec_path, 0o600)
    except:
        pass

def _load_token(key: str) -> Optional[str]:
    if HAS_KEYRING:
        try:
            v = keyring.get_password(SERVICE_NAME, key)
            if v is not None:
                return v
        except:
            pass
    sec_path = _secure_path()
    if not sec_path.exists():
        return None
    try:
        with open(sec_path, "rb") as f:
            raw = f.read()
        if HAS_DPAPI:
            raw = _dpapi_decrypt(raw)
        data = json.loads(raw.decode("utf-8"))
        return data.get(key)
    except:
        return None

def _delete_token(key: str):
    if HAS_KEYRING:
        try:
            keyring.delete_password(SERVICE_NAME, key)
        except:
            pass
    sec_path = _secure_path()
    if sec_path.exists():
        try:
            with open(sec_path, "rb") as f:
                raw = f.read()
            if HAS_DPAPI:
                raw = _dpapi_decrypt(raw)
            data = json.loads(raw.decode("utf-8"))
            data.pop(key, None)
            raw = json.dumps(data).encode("utf-8")
            if HAS_DPAPI:
                raw = _dpapi_encrypt(raw)
            with open(sec_path, "wb") as f:
                f.write(raw)
        except:
            pass

def save_token_bundle(uuid: str, bundle: Dict):
    # bundle contains access_token, refresh_token, xbox_token, xsts_token, minecraft_token, expires_at
    # Store each separately? Simplify: store as json string per uuid
    import json as js
    payload = js.dumps(bundle)
    _store_token(f"{uuid}:bundle", payload)

def load_token_bundle(uuid: str) -> Optional[Dict]:
    import json as js
    v = _load_token(f"{uuid}:bundle")
    if not v:
        return None
    try:
        return js.loads(v)
    except:
        return None

def delete_token_bundle(uuid: str):
    _delete_token(f"{uuid}:bundle")

def clear_all():
    meta = load_accounts_meta()
    for acc in meta:
        if acc.get("uuid"):
            delete_token_bundle(acc["uuid"])
    # clear files
    try:
        _accounts_path().unlink(missing_ok=True)
    except:
        pass
    try:
        _secure_path().unlink(missing_ok=True)
    except:
        pass
    if HAS_KEYRING:
        # keyring entries already deleted per uuid
        pass
