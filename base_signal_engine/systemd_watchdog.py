"""Minimal systemd-notify adapter for the permanent Hetzner Base worker.

Only one-way local AF_UNIX datagrams to systemd. No subprocesses, credentials,
network endpoints, hidden threads or lifecycle changes are started here.
"""
from __future__ import annotations

import os
import socket


class SystemdNotifier:
    def __init__(self, *, address: str | None = None):
        self._address = os.environ.get("NOTIFY_SOCKET", "") if address is None else address

    @property
    def enabled(self) -> bool:
        return bool(self._address)

    def send(self, message: str) -> bool:
        if not self._address:
            return False
        if not message or "\n" in message:
            raise ValueError("invalid systemd notification")
        address = ("\0" + self._address[1:]) if self._address.startswith("@") else self._address
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                client.sendto(message.encode("utf-8"), address)
            return True
        except OSError:
            # If the socket is missing, the real systemd watchdog intentionally
            # times out instead of faking a healthy process.
            return False

    def ready(self) -> bool:
        return self.send("READY=1")

    def progressed(self) -> bool:
        # Send only on a durably acknowledged transition or a finished healthy
        # cycle; never keep a stuck job alive with background heartbeat threads.
        return self.send("WATCHDOG=1")
