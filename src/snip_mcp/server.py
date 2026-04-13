"""snip_mcp MCP server - screen snipping via Ctrl+Shift+LeftClick."""

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import base64

from mcp.server.fastmcp import FastMCP, Context
from mcp.types import TextContent, ImageContent

from .capture import capture_region
from .config import SnipConfig
from .store import SnipStore

logger = logging.getLogger("snip_mcp")
logger.addHandler(logging.StreamHandler(sys.stderr))
logger.setLevel(logging.INFO)

if sys.platform != "win32":
    raise RuntimeError(
        "snip-mcp requires Windows. It uses Windows-specific APIs "
        "(global mouse hooks via ctypes) for screen capture."
    )


class SnipContext:
    """Shared state between lifespan and tool handlers."""

    def __init__(self, store: SnipStore, config: SnipConfig):
        self.store = store
        self.config = config
        self.process: asyncio.subprocess.Process | None = None
        self.new_snip_event = asyncio.Event()
        self._reader_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastMCP):
    config = SnipConfig.load()
    config.save_path.mkdir(parents=True, exist_ok=True)
    store = SnipStore(config.save_path, config.max_snips)
    ctx = SnipContext(store, config)

    # Build config JSON for listener subprocess
    listener_config = json.dumps({
        "overlay_alpha": config.overlay_alpha,
        "selection_color": config.selection_color,
        "selection_width": config.selection_width,
        "modifier_vk_codes": config.modifier_vk_codes,
    })

    listener_script = str(Path(__file__).parent / "listener.py")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, listener_script, listener_config,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
    )
    ctx.process = proc
    logger.info("Listener subprocess started (pid=%s)", proc.pid)

    async def read_listener():
        """Background task: read JSON lines from listener, capture screenshots."""
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode().strip()
                if not text:
                    continue
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from listener: %s", text)
                    continue

                if data.get("ready"):
                    logger.info("Listener ready")
                    continue
                if data.get("cancelled"):
                    logger.info("Snip cancelled: %s", data.get("reason", "unknown"))
                    ctx.new_snip_event.set()  # unblock waiting tool
                    continue

                # Capture the screen region (overlay is already hidden)
                await asyncio.sleep(0.05)  # compositor repaint delay
                try:
                    png_bytes = await asyncio.get_event_loop().run_in_executor(
                        None,
                        capture_region,
                        data["x"], data["y"], data["width"], data["height"],
                    )
                    info = store.add(png_bytes)
                    logger.info("Snip captured: %s (%d bytes)", info.name, info.size_bytes)

                    # Send toast notification to listener
                    toast_msg = json.dumps({"toast": f"✓ {info.name} captured"}) + "\n"
                    proc.stdin.write(toast_msg.encode())
                    await proc.stdin.drain()
                except Exception as e:
                    logger.error("Capture failed: %s", e)
                    continue

                ctx.new_snip_event.set()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Listener reader error: %s", e)

    ctx._reader_task = asyncio.create_task(read_listener())

    yield ctx

    # Shutdown
    if ctx._reader_task:
        ctx._reader_task.cancel()
    if proc.stdin:
        try:
            proc.stdin.write(b'{"shutdown":true}\n')
            await proc.stdin.drain()
        except Exception:
            pass
    try:
        proc.terminate()
    except ProcessLookupError:
        pass  # already exited
    try:
        await asyncio.wait_for(proc.wait(), timeout=3)
    except (asyncio.TimeoutError, ProcessLookupError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    logger.info("Listener subprocess stopped")


mcp = FastMCP("snip", lifespan=lifespan)


def _get_ctx(ctx: Context) -> SnipContext:
    return ctx.request_context.lifespan_context


@mcp.tool()
async def snip_screen(ctx: Context):
    """Open the snipping overlay to capture a screen region.

    The overlay will appear -- click and drag to select the area,
    then release to capture. Press Escape to cancel.
    """
    sctx = _get_ctx(ctx)
    proc = sctx.process

    if not proc or proc.returncode is not None:
        return "Listener process is not running"

    sctx.new_snip_event.clear()
    proc.stdin.write(b'{"activate":true}\n')
    await proc.stdin.drain()

    try:
        await asyncio.wait_for(sctx.new_snip_event.wait(), timeout=120)
    except asyncio.TimeoutError:
        return "Snip timed out -- no selection was made within 2 minutes"

    latest = sctx.store.get_latest()
    if latest is None:
        return "Snip was cancelled"

    name, png_bytes = latest
    info = sctx.store.get_info(name)
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return [
        TextContent(type="text", text=f"Captured {name} ({info.size_bytes} bytes)"),
        ImageContent(type="image", data=b64, mimeType="image/png"),
    ]


@mcp.tool()
async def get_snip(name: str, ctx: Context):
    """Retrieve a captured snip by name.

    Args:
        name: The name of the snip to retrieve.
    """
    sctx = _get_ctx(ctx)
    png_bytes = sctx.store.get(name)
    if png_bytes is None:
        available = [s.name for s in sctx.store.list_snips()[:5]]
        return f"No snip found with name '{name}'. Available: {available}"
    info = sctx.store.get_info(name)
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return [
        TextContent(type="text", text=f"{name} ({info.size_bytes} bytes)"),
        ImageContent(type="image", data=b64, mimeType="image/png"),
    ]


@mcp.tool()
async def get_latest_snip(ctx: Context):
    """Get the most recently captured snip."""
    sctx = _get_ctx(ctx)
    latest = sctx.store.get_latest()
    if latest is None:
        return "No snips captured yet"
    name, png_bytes = latest
    info = sctx.store.get_info(name)
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return [
        TextContent(type="text", text=f"{name} ({info.size_bytes} bytes)"),
        ImageContent(type="image", data=b64, mimeType="image/png"),
    ]


@mcp.tool()
async def list_snips(ctx: Context) -> str:
    """List all captured snips with names and timestamps."""
    sctx = _get_ctx(ctx)
    snips = sctx.store.list_snips()
    if not snips:
        return "No snips captured yet"
    lines = []
    for s in snips:
        lines.append(f"- {s.name} ({s.timestamp.strftime('%Y-%m-%d %H:%M:%S')}, {s.size_bytes} bytes)")
    return "\n".join(lines)


@mcp.tool()
async def rename_snip(old_name: str, new_name: str, ctx: Context) -> str:
    """Rename a captured snip.

    Args:
        old_name: Current name of the snip.
        new_name: New name for the snip.
    """
    sctx = _get_ctx(ctx)
    if sctx.store.rename(old_name, new_name):
        return f"Renamed '{old_name}' to '{new_name}'"
    return f"Failed to rename: '{old_name}' not found or '{new_name}' already exists"


@mcp.tool()
async def delete_snip(name: str, ctx: Context) -> str:
    """Delete a captured snip.

    Args:
        name: Name of the snip to delete.
    """
    sctx = _get_ctx(ctx)
    if sctx.store.delete(name):
        return f"Deleted snip '{name}'"
    return f"No snip found with name '{name}'"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
