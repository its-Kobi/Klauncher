from __future__ import annotations
import time, json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Callable

from launcher.auth.microsoft import request_device_code, poll_for_token, refresh_access_token, MicrosoftAuthError, CLIENT_ID
from launcher.auth.xbox import xbox_live_authenticate, xsts_authorize, XboxAuthError
from launcher.auth.minecraft import minecraft_login_with_xbox, get_minecraft_profile, check_entitlements, MinecraftAuthError, MinecraftOwnershipError
from launcher.auth.storage import save_accounts, load_accounts_meta, save_token_bundle, load_token_bundle, delete_token_bundle

@dataclass
class MinecraftProfile:
    uuid: str
    username: str
    xuid: Optional[str] = None

@dataclass
class MicrosoftAccount:
    uuid: str
    username: str
    xuid: Optional[str]
    expires_at: float
    # tokens stored securely, not in this dataclass plain, but bundle holds them
    account_type: str = "microsoft"

class MicrosoftAuthManager:
    def __init__(self):
        self._accounts: List[MicrosoftAccount] = []
        self._load()

    def _load(self):
        metas = load_accounts_meta()
        self._accounts = []
        for m in metas:
            try:
                self._accounts.append(MicrosoftAccount(
                    uuid=m["uuid"], username=m["username"], xuid=m.get("xuid"),
                    expires_at=m.get("expires_at", 0)
                ))
            except:
                continue

    def list_accounts(self) -> List[MicrosoftAccount]:
        return list(self._accounts)

    def get_account(self, uuid: str) -> Optional[MicrosoftAccount]:
        for a in self._accounts:
            if a.uuid == uuid:
                return a
        return None

    def _save_meta(self):
        metas = [{"uuid": a.uuid, "username": a.username, "xuid": a.xuid, "expires_at": a.expires_at} for a in self._accounts]
        save_accounts(metas)

    def login_device_flow(self, on_code: Callable[[str, str, int], None], cancel_check: Callable[[], bool] = None) -> MicrosoftAccount:
        # Step 1: Microsoft device code
        try:
            dc = request_device_code(CLIENT_ID)
        except MicrosoftAuthError as e:
            raise MicrosoftAuthError(f"Microsoft authentication failed: {e}") from e
        user_code = dc.get("user_code")
        verification_uri = dc.get("verification_uri") or dc.get("verification_url")
        interval = int(dc.get("interval", 5))
        expires_in = int(dc.get("expires_in", 900))
        device_code = dc.get("device_code")
        if not user_code or not verification_uri:
            raise MicrosoftAuthError("Invalid device code response from Microsoft")
        # Callback to UI to show code and open browser
        try:
            on_code(user_code, verification_uri, expires_in)
        except:
            pass
        # Step 2: poll for token (never log token)
        try:
            token_resp = poll_for_token(device_code, interval, expires_in, CLIENT_ID, cancel_check)
        except MicrosoftAuthError as e:
            # Map to user-friendly without exposing token
            msg = str(e)
            if "declined" in msg.lower() or "cancel" in msg.lower():
                raise MicrosoftAuthError("Authentication cancelled by user") from e
            if "expired" in msg.lower():
                raise MicrosoftAuthError("Authentication timed out. Please try again.") from e
            if "network" in msg.lower():
                raise MicrosoftAuthError("Network unavailable during Microsoft authentication. Please check your connection.") from e
            raise
        ms_access = token_resp.get("access_token")
        ms_refresh = token_resp.get("refresh_token")
        ms_expires = int(token_resp.get("expires_in", 3600))
        if not ms_access:
            raise MicrosoftAuthError("Microsoft authentication failed: no access token")

        # Step 3: Xbox Live
        try:
            xbox_resp = xbox_live_authenticate(ms_access)
            xbox_token = xbox_resp.get("Token")
            xbox_userhash = xbox_resp.get("DisplayClaims", {}).get("xui", [{}])[0].get("uhs")
            if not xbox_token or not xbox_userhash:
                raise XboxAuthError("Invalid Xbox Live response")
        except XboxAuthError as e:
            raise XboxAuthError(f"Xbox authentication failed: {e}") from e

        # Step 4: XSTS
        try:
            xsts_resp = xsts_authorize(xbox_token)
            xsts_token = xsts_resp.get("Token")
            xsts_userhash = xsts_resp.get("DisplayClaims", {}).get("xui", [{}])[0].get("uhs", xbox_userhash)
            xsts_xuid = xsts_resp.get("DisplayClaims", {}).get("xui", [{}])[0].get("xid")
            if not xsts_token:
                raise XboxAuthError("Invalid XSTS response")
        except XboxAuthError as e:
            # Provide user-friendly mapping without exposing tokens
            msg = str(e)
            if "child" in msg.lower() or "family" in msg.lower():
                raise XboxAuthError("Child account requires family approval. Please check Xbox family settings.") from e
            if "does not have an Xbox Live account" in msg:
                raise XboxAuthError("This Microsoft account does not have an Xbox Live account.") from e
            raise

        # Step 5: Minecraft services login
        try:
            mc_resp = minecraft_login_with_xbox(xsts_userhash, xsts_token)
            mc_access = mc_resp.get("access_token")
            mc_expires = int(mc_resp.get("expires_in", 86400))
            if not mc_access:
                raise MinecraftAuthError("Minecraft authentication failed: no access token")
        except MinecraftAuthError as e:
            raise

        # Step 6: Verify ownership via profile
        try:
            profile = get_minecraft_profile(mc_access)
            puuid = profile.get("id")
            pname = profile.get("name")
            if not puuid or not pname:
                raise MinecraftOwnershipError("This Microsoft account does not own Minecraft Java Edition. Please purchase Minecraft Java Edition or sign in with a Microsoft account that owns the game.")
            # Format uuid with dashes
            if len(puuid) == 32:
                puuid = f"{puuid[0:8]}-{puuid[8:12]}-{puuid[12:16]}-{puuid[16:20]}-{puuid[20:]}"
            # Optionally check entitlements, but profile success is definitive for ownership
            # If profile 404, get_minecraft_profile already raises MinecraftOwnershipError
        except MinecraftOwnershipError as e:
            raise MinecraftOwnershipError(str(e)) from e
        except MinecraftAuthError as e:
            raise MinecraftAuthError(f"Minecraft profile error: {e}") from e

        # Success: store account securely
        expires_at = time.time() + mc_expires
        # Update or create account
        existing = next((a for a in self._accounts if a.uuid == puuid), None)
        if existing:
            existing.username = pname
            existing.xuid = xsts_xuid
            existing.expires_at = expires_at
            acc = existing
        else:
            acc = MicrosoftAccount(uuid=puuid, username=pname, xuid=xsts_xuid, expires_at=expires_at)
            self._accounts.append(acc)
        self._save_meta()
        # Store token bundle securely (never in plain config)
        bundle = {
            "ms_access": ms_access,
            "ms_refresh": ms_refresh,
            "ms_expires_at": time.time() + ms_expires,
            "xbox_token": xbox_token,
            "xsts_token": xsts_token,
            "mc_access": mc_access,
            "mc_expires_at": expires_at,
            "xuid": xsts_xuid,
        }
        save_token_bundle(puuid, bundle)
        return acc

    def refresh_if_needed(self, uuid: str) -> Optional[dict]:
        acc = self.get_account(uuid)
        if not acc:
            return None
        bundle = load_token_bundle(uuid)
        if not bundle:
            return None
        # Check expiry with 5 min buffer
        if time.time() < bundle.get("mc_expires_at", 0) - 300:
            return bundle
        # Need refresh via Microsoft refresh_token
        ms_refresh = bundle.get("ms_refresh")
        if not ms_refresh:
            return bundle
        try:
            resp = refresh_access_token(ms_refresh, CLIENT_ID)
            new_ms_access = resp.get("access_token")
            new_ms_refresh = resp.get("refresh_token", ms_refresh)
            new_ms_expires = int(resp.get("expires_in", 3600))
            # Re-do Xbox/XSTS/Minecraft flow with new ms token
            xbox_resp = xbox_live_authenticate(new_ms_access)
            xbox_token = xbox_resp.get("Token")
            xbox_userhash = xbox_resp.get("DisplayClaims", {}).get("xui", [{}])[0].get("uhs")
            xsts_resp = xsts_authorize(xbox_token)
            xsts_token = xsts_resp.get("Token")
            xsts_userhash = xsts_resp.get("DisplayClaims", {}).get("xui", [{}])[0].get("uhs", xbox_userhash)
            mc_resp = minecraft_login_with_xbox(xsts_userhash, xsts_token)
            mc_access = mc_resp.get("access_token")
            mc_expires = int(mc_resp.get("expires_in", 86400))
            new_bundle = {
                "ms_access": new_ms_access,
                "ms_refresh": new_ms_refresh,
                "ms_expires_at": time.time() + new_ms_expires,
                "xbox_token": xbox_token,
                "xsts_token": xsts_token,
                "mc_access": mc_access,
                "mc_expires_at": time.time() + mc_expires,
                "xuid": bundle.get("xuid"),
            }
            save_token_bundle(uuid, new_bundle)
            # update meta expiry
            acc.expires_at = time.time() + mc_expires
            self._save_meta()
            return new_bundle
        except Exception:
            # Refresh failed, keep old bundle but mark expired
            return bundle

    def get_minecraft_token(self, uuid: str) -> Optional[str]:
        bundle = self.refresh_if_needed(uuid)
        if bundle:
            return bundle.get("mc_access")
        return None

    def get_access_token_for_launch(self, uuid: str) -> Optional[dict]:
        # Returns dict with username, uuid, access_token, xuid for launch
        acc = self.get_account(uuid)
        if not acc:
            return None
        bundle = self.refresh_if_needed(uuid)
        if not bundle or not bundle.get("mc_access"):
            return None
        return {
            "username": acc.username,
            "uuid": acc.uuid,
            "access_token": bundle["mc_access"],
            "xuid": acc.xuid or bundle.get("xuid"),
        }

    def logout(self, uuid: str):
        self._accounts = [a for a in self._accounts if a.uuid != uuid]
        self._save_meta()
        delete_token_bundle(uuid)

    def logout_all(self):
        for acc in list(self._accounts):
            delete_token_bundle(acc.uuid)
        self._accounts = []
        self._save_meta()
