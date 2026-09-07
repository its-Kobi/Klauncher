from __future__ import annotations
import json, urllib.request, urllib.error

class XboxAuthError(Exception):
    pass

def xbox_live_authenticate(access_token: str) -> dict:
    url = "https://user.auth.xboxlive.com/user/authenticate"
    body = {
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": f"d={access_token}"
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT"
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
        except:
            body = str(e)
        raise XboxAuthError(f"Xbox Live authentication failed: {body}") from e
    except Exception as e:
        raise XboxAuthError(f"Xbox Live network error: {e}") from e

def xsts_authorize(xbox_token: str) -> dict:
    url = "https://xsts.auth.xboxlive.com/xsts/authorize"
    body = {
        "Properties": {
            "SandboxId": "RETAIL",
            "UserTokens": [xbox_token]
        },
        "RelyingParty": "rp://api.minecraftservices.com/",
        "TokenType": "JWT"
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
            j = json.loads(body) if body else {}
            # Detect child account / no Xbox etc.
            xerr = j.get("XErr")
            msg = j.get("Message", body)
            if xerr == 2148916233:
                raise XboxAuthError("This Microsoft account does not have an Xbox Live account. Please create one at https://www.xbox.com") from e
            elif xerr in (2148916238, 2148916236, 2148916237):
                raise XboxAuthError("Child account requires family approval or adult verification. Please check Xbox family settings.") from e
            raise XboxAuthError(f"XSTS authorization failed: {msg}") from e
        except XboxAuthError:
            raise
        except:
            raise XboxAuthError(f"XSTS authorization failed: {e}") from e
    except Exception as e:
        raise XboxAuthError(f"XSTS network error: {e}") from e
