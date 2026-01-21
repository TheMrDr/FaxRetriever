"""
firewall_utils.py

Helpers to resolve LibertyServer and create Windows Firewall rules.
Best-effort: if rule creation fails due to permissions, return a flag indicating elevation is required.

This module avoids any UI; callers decide whether to prompt for elevation.
"""
from __future__ import annotations

import os
import socket
import subprocess
from typing import Optional, Tuple

from utils.logging_utils import get_logger

log = get_logger("firewall")


def resolve_hostname(hostname: str) -> Optional[str]:
    """Resolve hostname to first IPv4 address, or None if resolution fails."""
    try:
        name, aliases, addrs = socket.gethostbyname_ex(hostname)
        for ip in addrs:
            if "." in ip:  # naive IPv4 check
                return ip
    except Exception as e:
        try:
            log.info(f"Hostname resolution failed for {hostname}: {e}")
        except Exception:
            pass
    return None


def ensure_firewall_rule(name: str, port: int, remote_ip: str = "Any") -> Tuple[bool, str]:
    """
    Try to add an inbound firewall rule allowing TCP on `port` from `remote_ip` (default Any).
    Returns (ok, message). If permissions prevent creation, ok=False with a hint to elevate.
    """
    try:
        # Prefer PowerShell New-NetFirewallRule when available
        ps_cmd = (
            f"New-NetFirewallRule -DisplayName '{name}' -Direction Inbound -Action Allow "
            f"-Protocol TCP -LocalPort {port} -RemoteAddress {remote_ip} -Profile Any"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode == 0:
            return True, "rule_created"
        # Fall back to netsh
        rule_name = name.replace(" ", "_")
        netsh_cmd = [
            "netsh",
            "advfirewall",
            "firewall",
            "add",
            "rule",
            f"name={rule_name}",
            "dir=in",
            "action=allow",
            "protocol=TCP",
            f"localport={port}",
            f"remoteip={remote_ip}",
            "profile=any",
            "enable=yes",
        ]
        completed = subprocess.run(
            netsh_cmd,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode == 0:
            return True, "rule_created"
        msg = (completed.stderr or completed.stdout or "failed").strip()
        if "access is denied" in msg.lower():
            return False, "elevation_required"
        return False, msg
    except Exception as e:
        return False, f"error:{e.__class__.__name__}"


def build_rule_name(port: int) -> str:
    return f"FaxRetriever-LibertyRx-{port}"


def try_elevated_firewall_rule(name: str, port: int, remote_ip: str = "Any") -> Tuple[bool, str]:
    """
    Attempt to create the firewall rule via elevated PowerShell (UAC prompt).
    Returns (ok, message). ok indicates that we started an elevated process; it may still fail silently.
    """
    try:
        ps_inner = (
            f"New-NetFirewallRule -DisplayName '{name}' -Direction Inbound -Action Allow "
            f"-Protocol TCP -LocalPort {port} -RemoteAddress {remote_ip} -Profile Any"
        )
        # Start elevated PowerShell to run the command
        ps_cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Start-Process PowerShell -Verb RunAs -ArgumentList \"-NoProfile -Command {ps_inner}\"",
        ]
        completed = subprocess.run(
            ps_cmd,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode == 0:
            return True, "elevation_requested"
        msg = (completed.stderr or completed.stdout or "failed").strip()
        return False, msg
    except Exception as e:
        return False, f"error:{e.__class__.__name__}"
