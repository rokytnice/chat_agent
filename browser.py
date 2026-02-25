#!/usr/bin/env python3
"""Persistente MCP Playwright Browser-Session.

Startet den @playwright/mcp Server als SSE-Daemon und stellt
eine Python-Schnittstelle bereit, die den Browser persistent hält.
"""

import asyncio
import base64
import logging
import subprocess
import signal
import os
from pathlib import Path

log = logging.getLogger("telegram_bridge.browser")

WORKING_DIR = Path(__file__).parent
MCP_PORT = 8931
MCP_PROCESS: subprocess.Popen | None = None


def start_mcp_server() -> subprocess.Popen:
    """Startet den MCP Playwright Server als Hintergrundprozess."""
    global MCP_PROCESS

    # Falls schon laufend, erst beenden
    stop_mcp_server()

    cmd = [
        "npx", "@playwright/mcp@latest",
        "--port", str(MCP_PORT),
        "--headless",
        "--caps", "vision",
        "--shared-browser-context",
    ]
    log.info("Starte MCP Playwright Server: %s", " ".join(cmd))

    MCP_PROCESS = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(WORKING_DIR),
        start_new_session=True,
    )
    log.info("MCP Server gestartet PID=%d auf Port %d", MCP_PROCESS.pid, MCP_PORT)
    return MCP_PROCESS


def stop_mcp_server():
    """Beendet den MCP Server."""
    global MCP_PROCESS
    if MCP_PROCESS and MCP_PROCESS.poll() is None:
        log.info("Beende MCP Server PID=%d", MCP_PROCESS.pid)
        os.killpg(os.getpgid(MCP_PROCESS.pid), signal.SIGTERM)
        try:
            MCP_PROCESS.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(MCP_PROCESS.pid), signal.SIGKILL)
        MCP_PROCESS = None


def is_mcp_running() -> bool:
    """Prüft ob der MCP Server läuft (Port-Check)."""
    import socket
    try:
        with socket.create_connection(("localhost", MCP_PORT), timeout=2):
            return True
    except (ConnectionRefusedError, OSError):
        return False


async def mcp_call(tool_name: str, arguments: dict) -> dict:
    """Ruft ein MCP Tool über HTTP/SSE auf."""
    from mcp.client.sse import sse_client
    from mcp import ClientSession

    url = f"http://localhost:{MCP_PORT}/sse"

    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return result


async def navigate(url: str) -> str:
    """Navigiert zu einer URL und gibt den Snapshot zurück."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    await mcp_call("browser_navigate", {"url": url})
    result = await mcp_call("browser_snapshot", {})

    # Textinhalt extrahieren
    if hasattr(result, "content") and result.content:
        texts = []
        for item in result.content:
            if hasattr(item, "text"):
                texts.append(item.text)
        return "\n".join(texts) if texts else "(kein Inhalt)"
    return str(result)


async def screenshot(url: str = None) -> tuple[bytes | None, str]:
    """Macht einen Screenshot. Optional erst zu URL navigieren.

    Returns: (screenshot_bytes, snapshot_text)
    """
    if url:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        await mcp_call("browser_navigate", {"url": url})

    # Screenshot
    result = await mcp_call("browser_take_screenshot", {})
    img_bytes = None
    if hasattr(result, "content") and result.content:
        for item in result.content:
            if hasattr(item, "data"):
                img_bytes = base64.b64decode(item.data)
                break

    # Snapshot für Text
    snap = await mcp_call("browser_snapshot", {})
    snap_text = ""
    if hasattr(snap, "content") and snap.content:
        for item in snap.content:
            if hasattr(item, "text"):
                snap_text += item.text + "\n"

    return img_bytes, snap_text.strip()


async def click(element: str) -> str:
    """Klickt auf ein Element (Accessibility-Ref)."""
    await mcp_call("browser_click", {"element": element})
    result = await mcp_call("browser_snapshot", {})
    if hasattr(result, "content") and result.content:
        texts = [item.text for item in result.content if hasattr(item, "text")]
        return "\n".join(texts)
    return str(result)


async def type_text(element: str, text: str) -> str:
    """Tippt Text in ein Eingabefeld."""
    await mcp_call("browser_type", {"element": element, "text": text})
    result = await mcp_call("browser_snapshot", {})
    if hasattr(result, "content") and result.content:
        texts = [item.text for item in result.content if hasattr(item, "text")]
        return "\n".join(texts)
    return str(result)


async def list_tabs() -> str:
    """Listet offene Tabs."""
    result = await mcp_call("browser_tab_list", {})
    if hasattr(result, "content") and result.content:
        texts = [item.text for item in result.content if hasattr(item, "text")]
        return "\n".join(texts)
    return str(result)


async def get_snapshot() -> str:
    """Gibt den aktuellen Seiteninhalt als Accessibility-Snapshot zurück."""
    result = await mcp_call("browser_snapshot", {})
    if hasattr(result, "content") and result.content:
        texts = [item.text for item in result.content if hasattr(item, "text")]
        return "\n".join(texts)
    return str(result)
