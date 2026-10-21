import json
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

# The tunnel's own host; api.trycloudflare.com is the service cloudflared asks for one (it shows up in errors).
PUBLIC_URL = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")


class TunnelError(Exception):
    pass


class CloudflareQuickTunnel:
    """A public https URL for a local port, so phones can open the app from any network.

    Uses a Cloudflare "quick tunnel": no account needed, and the URL changes on every start.
    """

    def __init__(self, port: int):
        self._port = port
        self._process: subprocess.Popen[str] | None = None

    def start(self, timeout: float = 30) -> str:
        binary = shutil.which("cloudflared") or str(Path.home() / ".local/bin/cloudflared")
        if not Path(binary).exists():
            raise TunnelError("cloudflared is not installed: https://github.com/cloudflare/cloudflared/releases")
        self._process = subprocess.Popen(
            [binary, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self._port}"],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
        )
        found: list[str] = []
        failure: list[str] = []
        ready = threading.Event()

        def read_log() -> None:
            assert self._process and self._process.stderr
            for line in self._process.stderr:  # keep reading, or cloudflared blocks when the pipe fills up
                if not found and (match := PUBLIC_URL.search(line)):
                    found.append(match.group())
                    ready.set()
                elif "failed to request quick Tunnel" in line:
                    failure.append(line.strip())
            ready.set()  # cloudflared exited

        threading.Thread(target=read_log, daemon=True).start()
        if not ready.wait(timeout) or not found:
            self.stop()
            reason = failure[0] if failure else "no public URL after waiting"
            raise TunnelError(f"The tunnel could not open ({reason}). This network may block Cloudflare tunnels.")
        wait_until_resolvable(found[0].removeprefix("https://"), timeout)
        return found[0]

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._process.wait(timeout=5)


def wait_until_resolvable(host: str, timeout: float) -> bool:
    """Waits until public DNS knows the new tunnel host.

    Asking the Wi-Fi router too early makes it cache "no such host" for minutes, and every phone
    on that Wi-Fi would then fail to open the QR code. Cloudflare's DNS over HTTPS doesn't touch that cache.
    """
    query = "https://cloudflare-dns.com/dns-query?" + urllib.parse.urlencode({"name": host, "type": "A"})
    request = urllib.request.Request(query, headers={"accept": "application/dns-json"})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                if json.load(response).get("Answer"):
                    time.sleep(2)  # a moment for the other DNS servers to catch up
                    return True
        except OSError:
            pass
        time.sleep(1)
    return False
