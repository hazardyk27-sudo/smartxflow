#!/usr/bin/env python3
"""Hardened Hetzner WSGI entrypoint.

Install server-only PostgREST credential selection before importing ``app`` so
its module-level database bootstrap cannot instantiate the shared client with
the public anon credential.
"""

from core.web_supabase_server_credentials import install_web_server_service_role_guard

install_web_server_service_role_guard()

from app import app  # noqa: E402,F401  (must import after the runtime guard)
