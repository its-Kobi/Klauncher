from __future__ import annotations
import json, urllib.request, urllib.error

class MinecraftAuthError(Exception):
    pass

class MinecraftOwnershipError(MinecraftAuthError):
    pass

def minecraft_login_with_xbox(userhash: str, xsts_token: str) -> dict:
    url = "https://api.minecraftservices.com/authentication/login_with_xbox"
    body = {
        "identityToken": f"XBL3.0 x={userhash};{xsts_token}"
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
        raise MinecraftAuthError(f"Minecraft services authentication failed: {body}") from e
    except Exception as e:
        raise MinecraftAuthError(f"Minecraft services network error: {e}") from e

def check_entitlements(access_token: str) -> bool:
    # Verify ownership via entitlements/mcstore and profile
    # Entitlements check is optional; profile check is definitive
    url = "https://api.minecraftservices.com/entitlements/mcstore"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            j = json.loads(resp.read().decode())
            items = j.get("items", [])
            for item in items:
                name = item.get("name","")
                if "product_minecraft" in name or "game_minecraft" in name:
                    return True
            # If no product, still check profile as entitlement check can be flaky for Game Pass
            return False
    except urllib.error.HTTPError as e:
        # If 401/403, treat as not owned
        return False
    except:
        return False

def get_minecraft_profile(access_token: str) -> dict:
    url = "https://api.minecraftservices.com/minecraft/profile"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
            j = json.loads(body) if body else {}
            if e.code == 404:
                raise MinecraftOwnershipError("This Microsoft account does not own Minecraft Java Edition. Please purchase Minecraft Java Edition or sign in with a Microsoft account that owns the game.") from e
            raise MinecraftAuthError(f"Failed to retrieve Minecraft profile: {body}") from e
        except MinecraftOwnershipError:
            raise
        except:
            raise MinecraftAuthError(f"Failed to retrieve Minecraft profile: {e}") from e
    except Exception as e:
        raise MinecraftAuthError(f"Minecraft profile network error: {e}") from e
