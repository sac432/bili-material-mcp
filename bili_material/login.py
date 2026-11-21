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

from bilibili_api import login_v2

from .client import load_credential, save_credential  # also selects the HTTP client
from .config import Settings


async def _login(settings: Settings) -> int:
    qr = login_v2.QrCodeLogin(login_v2.QrCodeLoginChannel.WEB)
    await qr.generate_qrcode()
    png = settings.data_dir / "login_qrcode.png"
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    qr.get_qrcode_picture().to_file(str(png))
    print(qr.get_qrcode_terminal())
    print(f"Scan with the Bilibili app (secondary account recommended).")
    print(f"If the terminal QR code is unreadable, open: {png}")
    last = None
    try:
        while True:
            state = await qr.check_state()
            if state != last:
                print(f"status: {state.name}")
                last = state
            if state == login_v2.QrCodeLoginEvents.DONE:
                break
            if state == login_v2.QrCodeLoginEvents.TIMEOUT:
                print("QR code expired; run the command again.")
                return 1
            await asyncio.sleep(2)
    finally:
        png.unlink(missing_ok=True)
    save_credential(settings, qr.get_credential())
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
