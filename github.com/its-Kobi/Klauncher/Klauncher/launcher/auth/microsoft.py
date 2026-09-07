from __future__ import annotations
import time, urllib.parse, urllib.request, json
from typing import Dict, Optional, Callable

# Prism Launcher's public client ID (from CMakeLists.txt)
CLIENT_ID = "c36a9fb6-4f2a-41ff-90bd-ae7cc92031eb"
SCOPE = "XboxLive.signin offline_access"
DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"

class MicrosoftAuthError(Exception):
    pass

def request_device_code(client_id: str = CLIENT_ID) -> Dict:
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "scope": SCOPE,
    }).encode()
    req = urllib.request.Request(DEVICE_CODE_URL, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            j = json.loads(body)
            # expected: device_code, user_code, verification_uri, expires_in, interval
            return j
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
        except:
            body = str(e)
        raise MicrosoftAuthError(f"Failed to request device code: {body}") from e
    except Exception as e:
        raise MicrosoftAuthError(f"Network error requesting device code: {e}") from e

def poll_for_token(device_code: str, interval: int = 5, expires_in: int = 900, client_id: str = CLIENT_ID, cancel_check: Optional[Callable[[], bool]] = None) -> Dict:
    end = time.time() + expires_in
    data_base = {
        "client_id": client_id,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": device_code,
    }
    while time.time() < end:
        if cancel_check and cancel_check():
            raise MicrosoftAuthError("Authentication cancelled by user")
        time.sleep(interval)
        data = urllib.parse.urlencode(data_base).encode()
        req = urllib.request.Request(TOKEN_URL, data=data, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode()
                j = json.loads(body)
                if "access_token" in j:
                    return j
                # error handling
                err = j.get("error")
                if err == "authorization_pending":
                    continue
                elif err == "slow_down":
                    interval += 2
                    continue
                elif err == "expired_token":
                    raise MicrosoftAuthError("Device code expired. Please try again.")
                elif err == "authorization_declined":
                    raise MicrosoftAuthError("Authorization declined by user")
                else:
                    raise MicrosoftAuthError(f"Microsoft authentication failed: {err}")
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode()
                j = json.loads(body)
                err = j.get("error")
                if err == "authorization_pending":
                    continue
                elif err == "slow_down":
                    interval += 2
                    continue
                elif err == "expired_token":
                    raise MicrosoftAuthError("Device code expired") from e
                elif err == "authorization_declined":
                    raise MicrosoftAuthError("Authorization declined") from e
                # For other HTTP errors, treat as pending and retry a few times
                continue
            except MicrosoftAuthError:
                raise
            except:
                continue
        except MicrosoftAuthError:
            raise
        except Exception:
            # network transient, continue polling
            continue
    raise MicrosoftAuthError("Authentication timed out")

def refresh_access_token(refresh_token: str, client_id: str = CLIENT_ID) -> Dict:
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": SCOPE,
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            j = json.loads(body)
            if "access_token" in j:
                return j
            raise MicrosoftAuthError(f"Refresh failed: {j.get('error_description', j.get('error','unknown'))}")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
            j = json.loads(body)
            raise MicrosoftAuthError(f"Refresh failed: {j.get('error_description', body)}") from e
        except MicrosoftAuthError:
            raise
        except Exception as ex:
            raise MicrosoftAuthError(f"Refresh network error: {ex}") from ex
