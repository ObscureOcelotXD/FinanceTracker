"""Sync portfolio.csv via Umbrel Files API (dashboard) or a local/SMB path.

Stock Umbrel File Browser sits behind app-proxy; the dashboard proxy cookie often
returns 401 for :7421 API calls. Umbrel's built-in Files API on the dashboard
(port 80) accepts the JWT from user.login and can read/write
/Home/Documents/... — the same Documents folder you see in the UI / File Browser.
"""
from __future__ import annotations

import base64
import json
import os
import posixpath
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import requests

from api import portfolio_import as pi


DEFAULT_FILENAME = "portfolio.csv"
DEFAULT_REMOTE_DIR = "/Home/Documents/Portfolio"


def sync_filename() -> str:
    name = (os.getenv("PORTFOLIO_SYNC_FILENAME") or DEFAULT_FILENAME).strip()
    return name or DEFAULT_FILENAME


def sync_dir() -> Optional[Path]:
    raw = (os.getenv("PORTFOLIO_SYNC_DIR") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def sync_file_path() -> Optional[Path]:
    root = sync_dir()
    if root is None:
        return None
    return root / sync_filename()


def _umbrel_host() -> str:
    return (
        (os.getenv("PORTFOLIO_FB_HOST") or "").strip()
        or (os.getenv("UMBREL_TAILSCALE_IP") or "").strip()
        or (os.getenv("UMBREL_HOST") or "").strip()
    )


def umbrel_dashboard_base_url() -> Optional[str]:
    explicit = (os.getenv("UMBREL_DASHBOARD_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    host = _umbrel_host()
    if not host:
        return None
    scheme = (os.getenv("PORTFOLIO_FB_SCHEME") or "http").strip() or "http"
    # Strip accidental :7421 — Files API is on the dashboard, not File Browser port.
    if ":" in host and not host.startswith("["):
        host = host.split(":")[0]
    return f"{scheme}://{host}"


def umbrel_password() -> Optional[str]:
    return (
        (os.getenv("UMBREL_PASSWORD") or "").strip()
        or (os.getenv("PORTFOLIO_UMBREL_PASSWORD") or "").strip()
        or None
    )


def umbrel_totp() -> Optional[str]:
    raw = (os.getenv("UMBREL_TOTP") or os.getenv("PORTFOLIO_UMBREL_TOTP") or "").strip()
    return raw or None


def remote_dir() -> str:
    # Prefer new name; keep PORTFOLIO_FB_PATH as alias for existing configs.
    raw = (
        (os.getenv("PORTFOLIO_UMBREL_PATH") or "").strip()
        or (os.getenv("PORTFOLIO_FB_PATH") or "").strip()
        or DEFAULT_REMOTE_DIR
    )
    path = "/" + raw.strip("/")
    # Old File Browser path /Documents/... → Umbrel Files /Home/Documents/...
    if path == "/Documents" or path.startswith("/Documents/"):
        path = "/Home" + path
    return path


def remote_file() -> str:
    return f"{remote_dir().rstrip('/')}/{sync_filename()}"


def uses_umbrel_files() -> bool:
    return umbrel_dashboard_base_url() is not None and umbrel_password() is not None


def is_configured() -> bool:
    return uses_umbrel_files() or sync_dir() is not None


def _path_reachable(path: Path) -> bool:
    try:
        probe = path
        while True:
            if probe.exists():
                return True
            parent = probe.parent
            if parent == probe:
                return False
            probe = parent
    except OSError:
        return False


def _looks_like_html(resp: requests.Response) -> bool:
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "text/html" in ctype:
        return True
    text = (resp.text or "")[:200].lstrip().lower()
    return text.startswith("<!doctype") or text.startswith("<html")


def _umbrel_login(session: requests.Session) -> str:
    """Log into Umbrel OS; return API Bearer JWT (not the proxy cookie)."""
    password = umbrel_password()
    dash = umbrel_dashboard_base_url()
    if not password or not dash:
        raise ValueError(
            "Set UMBREL_TAILSCALE_IP and UMBREL_PASSWORD (Umbrel dashboard password)."
        )

    payload: dict[str, str] = {"password": password}
    totp = umbrel_totp()
    if totp:
        payload["totpToken"] = totp

    url = f"{dash}/trpc/user.login"
    resp = session.post(url, json=payload, timeout=30)
    if _looks_like_html(resp):
        raise ConnectionError(f"Umbrel login returned HTML at {url}")
    if resp.status_code >= 400:
        raise ConnectionError(f"Umbrel login failed ({resp.status_code}): {resp.text[:200]}")
    try:
        data = resp.json()
    except Exception as exc:
        raise ConnectionError(f"Umbrel login returned non-JSON: {resp.text[:200]}") from exc
    if data.get("error"):
        raise ConnectionError(f"Umbrel login error: {data['error']}")
    token = (data.get("result") or {}).get("data")
    if not isinstance(token, str) or not token:
        raise ConnectionError(f"Umbrel login missing token: {resp.text[:200]}")
    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _trpc_ok(resp: requests.Response, what: str) -> Any:
    if _looks_like_html(resp):
        raise ConnectionError(f"{what}: got HTML instead of Umbrel API response")
    if resp.status_code >= 400:
        raise ConnectionError(f"{what} failed ({resp.status_code}): {resp.text[:200]}")
    try:
        data = resp.json()
    except Exception as exc:
        raise ConnectionError(f"{what}: non-JSON response: {resp.text[:200]}") from exc
    if data.get("error"):
        err = data["error"]
        msg = err.get("message") if isinstance(err, dict) else err
        raise ConnectionError(f"{what} failed: {msg}")
    return (data.get("result") or {}).get("data")


def _ensure_remote_dir(session: requests.Session, dash: str, token: str, directory: str) -> None:
    """Create each path segment under /Home/... if missing."""
    parts = [p for p in directory.strip("/").split("/") if p]
    built = ""
    headers = _auth_headers(token)
    for part in parts:
        built = f"{built}/{part}"
        # Skip creating virtual roots that already exist (/Home, etc.)
        list_url = f"{dash}/trpc/files.list?input={quote(json.dumps({'path': built}))}"
        listed = session.get(list_url, headers=headers, timeout=30)
        if listed.status_code < 400 and not (listed.json() if listed.text else {}).get("error"):
            continue
        create = session.post(
            f"{dash}/trpc/files.createDirectory",
            json={"path": built},
            headers=headers,
            timeout=30,
        )
        # Ignore "already exists" style failures if list races.
        if create.status_code >= 400 or (create.text and '"error"' in create.text[:80]):
            # Re-check; if list works now, continue.
            listed2 = session.get(list_url, headers=headers, timeout=30)
            try:
                _trpc_ok(listed2, f"List {built}")
            except ConnectionError:
                _trpc_ok(create, f"Create folder {built}")


def _upload_file(session: requests.Session, dash: str, token: str, remote: str, body: str) -> None:
    url = (
        f"{dash}/api/files/upload"
        f"?path={quote(remote, safe='')}"
        f"&collision=replace"
    )
    headers = {
        **_auth_headers(token),
        "Content-Type": "text/csv; charset=utf-8",
    }
    resp = session.post(url, data=body.encode("utf-8"), headers=headers, timeout=60)
    if _looks_like_html(resp):
        raise ConnectionError("Upload returned Umbrel HTML — check UMBREL_PASSWORD / host.")
    if resp.status_code >= 400:
        raise ConnectionError(f"Upload failed ({resp.status_code}): {resp.text[:200]}")


def _download_file(session: requests.Session, dash: str, token: str, remote: str) -> str:
    url = f"{dash}/api/files/download?path={quote(remote, safe='')}"
    resp = session.get(url, headers=_auth_headers(token), timeout=60)
    if _looks_like_html(resp):
        raise ConnectionError("Download returned Umbrel HTML — check UMBREL_PASSWORD / host.")
    if resp.status_code == 404:
        raise FileNotFoundError(
            f"No portfolio file at {remote} on Umbrel. Push first or create it in Files."
        )
    if resp.status_code >= 400:
        raise ConnectionError(f"Download failed ({resp.status_code}): {resp.text[:200]}")
    return resp.content.decode("utf-8-sig")


def _probe_exists(session: requests.Session, dash: str, token: str, remote: str) -> bool:
    parent = posixpath.dirname(remote.rstrip("/")) or "/"
    name = posixpath.basename(remote.rstrip("/"))
    list_url = f"{dash}/trpc/files.list?input={quote(json.dumps({'path': parent}))}"
    resp = session.get(list_url, headers=_auth_headers(token), timeout=15)
    try:
        data = _trpc_ok(resp, "List parent")
    except ConnectionError:
        return False
    files = (data or {}).get("files") or []
    return any(f.get("name") == name for f in files)


def status() -> dict[str, Any]:
    if uses_umbrel_files():
        dash = umbrel_dashboard_base_url()
        remote = remote_file()
        assert dash
        try:
            with requests.Session() as session:
                token = _umbrel_login(session)
                exists = _probe_exists(session, dash, token, remote)
            message = (
                f"Umbrel Files ready at {dash} → {remote}"
                if exists
                else f"Umbrel Files reachable at {dash} — push to create {remote}"
            )
            return {
                "configured": True,
                "mode": "umbrel_files",
                "path": dash,
                "file": remote,
                "exists": exists,
                "reachable": True,
                "message": message,
            }
        except Exception as exc:
            return {
                "configured": True,
                "mode": "umbrel_files",
                "path": dash,
                "file": remote,
                "exists": False,
                "reachable": False,
                "message": f"Umbrel Files not reachable ({dash}): {exc}",
            }

    if _umbrel_host() and not umbrel_password():
        return {
            "configured": True,
            "mode": "umbrel_files",
            "path": umbrel_dashboard_base_url(),
            "file": remote_file(),
            "exists": False,
            "reachable": False,
            "message": (
                "Host set but UMBREL_PASSWORD is missing. "
                "Set your Umbrel dashboard password (see docs/PORTFOLIO_SYNC.md)."
            ),
        }

    root = sync_dir()
    if root is None:
        return {
            "configured": False,
            "mode": None,
            "path": None,
            "file": None,
            "exists": False,
            "reachable": False,
            "message": (
                "Not configured. Set UMBREL_TAILSCALE_IP and UMBREL_PASSWORD "
                "(Umbrel dashboard password) — see docs/PORTFOLIO_SYNC.md."
            ),
        }
    file_path = root / sync_filename()
    reachable = _path_reachable(root)
    exists = reachable and file_path.is_file()
    if not reachable:
        message = f"Path not reachable: {root}."
    elif exists:
        message = f"Sync file ready at {file_path}"
    else:
        message = f"Folder reachable at {root} — push to create {sync_filename()}"
    return {
        "configured": True,
        "mode": "path",
        "path": str(root),
        "file": str(file_path),
        "exists": exists,
        "reachable": reachable,
        "message": message,
    }


def ensure_sync_dir() -> Path:
    root = sync_dir()
    if root is None:
        raise ValueError("PORTFOLIO_SYNC_DIR is not set.")
    if not _path_reachable(root):
        raise FileNotFoundError(f"Cannot reach {root}.")
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise FileNotFoundError(f"Could not create/open {root}: {exc}") from exc
    return root


def push_portfolio_csv() -> dict[str, Any]:
    body = pi.export_portfolio_csv()
    if uses_umbrel_files():
        dash = umbrel_dashboard_base_url()
        directory = remote_dir()
        target = remote_file()
        assert dash
        with requests.Session() as session:
            token = _umbrel_login(session)
            _ensure_remote_dir(session, dash, token, directory)
            _upload_file(session, dash, token, target, body)
            downloaded = _download_file(session, dash, token, target)
            if "ticker" not in downloaded.lower() and "type" not in downloaded.lower():
                raise ConnectionError(
                    "Upload appeared to succeed but remote file does not look like a portfolio CSV."
                )
        return {
            "ok": True,
            "action": "push",
            "mode": "umbrel_files",
            "file": target,
            "bytes": len(body.encode("utf-8")),
            "message": (
                f"Pushed portfolio CSV to Umbrel Files {target} "
                f"(Documents → Portfolio in Umbrel Files / File Browser — refresh)."
            ),
        }

    root = ensure_sync_dir()
    target_path = root / sync_filename()
    target_path.write_text(body, encoding="utf-8")
    return {
        "ok": True,
        "action": "push",
        "mode": "path",
        "file": str(target_path),
        "bytes": len(body.encode("utf-8")),
        "message": f"Pushed portfolio CSV to {target_path}",
    }


def pull_portfolio_csv() -> dict[str, Any]:
    if uses_umbrel_files():
        dash = umbrel_dashboard_base_url()
        target = remote_file()
        assert dash
        with requests.Session() as session:
            token = _umbrel_login(session)
            text = _download_file(session, dash, token, target)
        raw = base64.b64encode(text.encode("utf-8")).decode("ascii")
        contents = f"data:text/csv;base64,{raw}"
        result = pi.apply_auto_upload(contents, sync_filename())
        result["action"] = "pull"
        result["mode"] = "umbrel_files"
        result["file"] = target
        if result.get("errors") and not result.get("detected"):
            result["ok"] = False
            result["message"] = "Pull failed — see errors."
        else:
            result["ok"] = True
            result["message"] = f"Pulled and applied {target} from Umbrel Files"
        return result

    target_path = sync_file_path()
    if target_path is None:
        raise ValueError(
            "Portfolio sync is not configured. Set UMBREL_TAILSCALE_IP + UMBREL_PASSWORD "
            "or PORTFOLIO_SYNC_DIR."
        )
    if not target_path.is_file():
        raise FileNotFoundError(f"No portfolio file at {target_path}.")
    text = target_path.read_text(encoding="utf-8-sig")
    raw = base64.b64encode(text.encode("utf-8")).decode("ascii")
    contents = f"data:text/csv;base64,{raw}"
    result = pi.apply_auto_upload(contents, target_path.name)
    result["action"] = "pull"
    result["mode"] = "path"
    result["file"] = str(target_path)
    if result.get("errors") and not result.get("detected"):
        result["ok"] = False
        result["message"] = "Pull failed — see errors."
    else:
        result["ok"] = True
        result["message"] = f"Pulled and applied {target_path}"
    return result


# Back-compat aliases used by older tests / imports
def filebrowser_base_url() -> Optional[str]:
    return umbrel_dashboard_base_url()


def uses_filebrowser() -> bool:
    return uses_umbrel_files()
