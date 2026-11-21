"""Interactive QR-code login. Saves the credential to the local data directory.

Usage:
    python -m bili_material.login          # log in (QR code in terminal + PNG file)
    python -m bili_material.login --check  # verify the saved credential
    python -m bili_material.login --logout # delete the saved credential

Use a secondary account. The saved file contains session cookies and must never
be committed or shared.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from urllib.parse import parse_qs, urlparse

import aiohttp
import qrcode
import qrcode_terminal
from bilibili_api import Credential

from .client import UA, load_credential, save_credential
from .config import Settings

# bilibili-api's QrCodeLogin.check_state only parses cookies from the redirect
# URL query string; Bilibili now delivers them via Set-Cookie, which leaves
# every field empty. This module polls the web QR endpoints directly and reads
# both sources.
GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate?source=main-fe-header"
POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
STATES = {86101: "waiting for scan", 86090: "scanned, confirm on phone", 86038: "expired", 0: "done"}


def _extract(resp: aiohttp.ClientResponse, data: dict) -> dict[str, str]:
    found: dict[str, str] = {}
    for name, morsel in resp.cookies.items():
        found[name.lower()] = morsel.value
    url = data.get("url") or ""
    for name, values in parse_qs(urlparse(url).query).items():
        if values and values[0]:
            found.setdefault(name.lower(), values[0])
    if data.get("refresh_token"):
        found["ac_time_value"] = data["refresh_token"]
    return found


async def _login(settings: Settings) -> int:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    png = settings.data_dir / "login_qrcode.png"
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": UA}) as s:
        async with s.get(GENERATE_URL) as r:
            gen = (await r.json(content_type=None))["data"]
        link, key = gen["url"], gen["qrcode_key"]
        qrcode.make(link).save(str(png))
        print(qrcode_terminal.qr_terminal_str(link))
        print("Scan with the Bilibili app (secondary account recommended).")
        print(f"If the terminal QR code is unreadable, open: {png}")
        last = None
        try:
            while True:
                async with s.get(POLL_URL, params={"qrcode_key": key}) as r:
                    data = (await r.json(content_type=None)).get("data") or {}
                    code = data.get("code")
                    if code != last:
                        print(f"status: {STATES.get(code, code)}")
                        last = code
                    if code == 0:
                        fields = _extract(r, data)
                        break
                if code == 86038:
                    print("QR code expired; run the command again.")
                    return 1
                await asyncio.sleep(2)
        finally:
            png.unlink(missing_ok=True)

    print(f"received fields: {sorted(fields)}")  # names only, never values
    if not fields.get("sessdata"):
        print("Login reported success but no SESSDATA was found; nothing saved.")
        return 1
    cred = Credential(
        sessdata=fields.get("sessdata"),
        bili_jct=fields.get("bili_jct"),
        dedeuserid=fields.get("dedeuserid"),
        ac_time_value=fields.get("ac_time_value"),
    )
    save_credential(settings, cred)
    print(f"Saved credential to {settings.credential_file}")
    return 0


async def _check(settings: Settings) -> int:
    cred = load_credential(settings)
    if cred is None:
        print("No saved credential.")
        return 1
    ok = await cred.check_valid()
    print("Credential is valid." if ok else "Credential is invalid or expired; log in again.")
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify the saved credential")
    parser.add_argument("--logout", action="store_true", help="delete the saved credential")
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.logout:
        settings.credential_file.unlink(missing_ok=True)
        print("Credential removed.")
        sys.exit(0)
    sys.exit(asyncio.run(_check(settings) if args.check else _login(settings)))


if __name__ == "__main__":
    main()
