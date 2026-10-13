from __future__ import annotations

import os
import socket
import threading
from typing import Any, Callable, Dict, Optional

import requests


_TRUE = {"1", "true", "yes", "on"}
_DEFAULT_LEASE_NAME = "prematch-production"
_DEFAULT_TTL_SECONDS = 420
_DEFAULT_LOCAL_LOCK = "/tmp/smartxflow_prematch_writer.lock"


def _authoritative_enabled() -> bool:
    return str(
        os.environ.get("SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE") or ""
    ).strip().lower() in _TRUE


def _runtime_id(runtime_module=None) -> str:
    explicit = str(os.environ.get("SMARTXFLOW_RUNTIME_ID") or "").strip()
    if explicit:
        return explicit

    source = ""
    if runtime_module is not None:
        source = str(getattr(runtime_module, "SCRAPER_SOURCE", "") or "").strip()
    if source:
        return source

    if os.environ.get("REPL_ID") or os.environ.get("REPL_SLUG") or os.environ.get("REPL_OWNER"):
        return "replit-preview"
    return f"host:{socket.gethostname()}"


def _lease_ttl_seconds() -> int:
    raw = str(os.environ.get("SMARTXFLOW_PREMATCH_LEASE_TTL_SECONDS") or "").strip()
    try:
        value = int(raw) if raw else _DEFAULT_TTL_SECONDS
    except ValueError:
        value = _DEFAULT_TTL_SECONDS
    return max(120, min(value, 1800))


def acquire_runtime_lease(
    supabase_url: str,
    service_role_key: str,
    holder: str,
    *,
    ttl_seconds: Optional[int] = None,
    lease_name: str = _DEFAULT_LEASE_NAME,
    request_post: Callable[..., Any] = requests.post,
) -> Dict[str, Any]:
    """Atomically acquire/renew the production prematch lease via service-role RPC."""
    url = str(supabase_url or "").rstrip("/")
    key = str(service_role_key or "").strip()
    holder = str(holder or "").strip()
    lease_name = str(lease_name or "").strip()
    ttl = int(ttl_seconds or _lease_ttl_seconds())

    if not url or not key or not holder or not lease_name:
        return {
            "acquired": False,
            "holder": None,
            "lease_until": None,
            "error": "lease_credentials_or_identity_missing",
        }

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "p_lease_name": lease_name,
        "p_holder": holder,
        "p_ttl_seconds": ttl,
    }

    try:
        response = request_post(
            f"{url}/rest/v1/rpc/acquire_scraper_runtime_lease",
            headers=headers,
            json=payload,
            timeout=10,
        )
    except Exception as exc:
        return {
            "acquired": False,
            "holder": None,
            "lease_until": None,
            "error": f"lease_rpc_request:{str(exc)[:180]}",
        }

    if response.status_code != 200:
        return {
            "acquired": False,
            "holder": None,
            "lease_until": None,
            "error": f"lease_rpc_http_{response.status_code}:{str(getattr(response, 'text', '') or '')[:180]}",
        }

    try:
        body = response.json()
    except Exception as exc:
        return {
            "acquired": False,
            "holder": None,
            "lease_until": None,
            "error": f"lease_rpc_json:{str(exc)[:180]}",
        }

    if isinstance(body, list):
        body = body[0] if body else {}
    if not isinstance(body, dict):
        body = {}

    return {
        "acquired": bool(body.get("acquired")),
        "holder": body.get("holder"),
        "lease_until": body.get("lease_until"),
        "error": body.get("error"),
    }


def _try_local_lock():
    path = str(
        os.environ.get("SMARTXFLOW_PREMATCH_LOCAL_LOCK_PATH") or _DEFAULT_LOCAL_LOCK
    ).strip()
    try:
        import fcntl

        handle = open(path, "a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return None
        return handle
    except Exception:
        return None


def _release_local_lock(handle) -> None:
    if handle is None:
        return
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        handle.close()
    except Exception:
        pass


def install_authoritative_atomic_lease_guard(runtime_module) -> None:
    """Wrap legacy ``main`` with a cross-host atomic lease and same-host flock.

    This is intentionally installed by the authoritative bootstrap before the
    long-running loop starts. Legacy/non-authoritative execution is untouched.
    """
    if getattr(runtime_module, "_smartxflow_atomic_lease_installed", False):
        return

    original_main = runtime_module.main
    original_check_master = runtime_module.check_master_status
    state = {"lease_acquired": False}

    def guarded_check_master(supabase_url: str, supabase_key: str):
        if state["lease_acquired"]:
            return True, "atomic_db_lease"
        return original_check_master(supabase_url, supabase_key)

    def guarded_main():
        if not _authoritative_enabled():
            return original_main()

        local_lock = _try_local_lock()
        if local_lock is None:
            print("[AtomicLease] Başka bir local prematch writer aktif; standby")
            return False

        supabase_url = str(os.environ.get("SUPABASE_URL") or "").strip()
        service_role = str(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        holder = _runtime_id(runtime_module)
        ttl = _lease_ttl_seconds()

        result = acquire_runtime_lease(
            supabase_url,
            service_role,
            holder,
            ttl_seconds=ttl,
        )
        if not result.get("acquired"):
            reason = result.get("error") or (
                f"held_by={result.get('holder')} until={result.get('lease_until')}"
            )
            print(f"[AtomicLease] Lease alınamadı; fail-closed standby: {reason}")
            _release_local_lock(local_lock)
            return False

        print(
            f"[AtomicLease] Acquired holder={holder} "
            f"until={result.get('lease_until') or 'unknown'}"
        )
        state["lease_acquired"] = True
        stop_event = threading.Event()

        def renew_loop() -> None:
            interval = max(30, min(120, ttl // 3))
            while not stop_event.wait(interval):
                renewed = acquire_runtime_lease(
                    supabase_url,
                    service_role,
                    holder,
                    ttl_seconds=ttl,
                )
                if not renewed.get("acquired"):
                    print(
                        "[AtomicLease] HATA — lease renewal failed; "
                        f"{renewed.get('error') or renewed}"
                    )
                    return

        renewer = threading.Thread(
            target=renew_loop,
            name="prematch-lease-renewer",
            daemon=True,
        )
        renewer.start()

        try:
            return original_main()
        finally:
            stop_event.set()
            renewer.join(timeout=1.0)
            state["lease_acquired"] = False
            _release_local_lock(local_lock)

    runtime_module.check_master_status = guarded_check_master
    runtime_module.main = guarded_main
    runtime_module._smartxflow_atomic_lease_installed = True
