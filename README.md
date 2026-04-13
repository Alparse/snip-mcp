# snip-mcp

An MCP server that lets you capture screen regions directly into your Claude Code conversations. Select any area of your screen using a hotkey or tool call, and the screenshot is immediately available as an image in context.

## Features

- **Hotkey capture** -- Ctrl+Shift+Click opens a snipping overlay anywhere, anytime
- **Tool-triggered capture** -- Claude can invoke the snipping tool on your behalf
- **Multi-monitor support** -- works across all connected displays with DPI awareness
- **Persistent storage** -- snips are saved to disk and survive server restarts
- **Auto-pruning** -- configurable limit prevents unbounded storage growth
- **Toast notifications** -- visual confirmation when a snip is captured

## Requirements

- **Windows 10 or later** (uses Windows-specific global mouse hooks via ctypes)
- **Python 3.11+**

## Installation

```bash
git clone https://github.com/Alparse/snip-mcp.git
cd snip-mcp
pip install -e .
```

Or with uv:

```bash
git clone https://github.com/Alparse/snip-mcp.git
cd snip-mcp
uv pip install -e .
```

## Claude Code Configuration

Add the server to your Claude Code MCP settings.

### If installed via pip (global or venv)

In `~/.claude/settings.json` (global) or `.claude/settings.json` (project):

```json
{
  "mcpServers": {
    "snip": {
      "command": "snip-mcp"
    }
  }
}
```

### If using uv (recommended for isolation)

```json
{
  "mcpServers": {
    "snip": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/snip-mcp", "snip-mcp"]
    }
  }
}
```

## Usage

### Hotkey capture

Press **Ctrl+Shift+Left Click** anywhere on screen to open the snipping overlay:

1. Click and drag to select a region
2. Release to capture
3. Press **Escape** to cancel

A toast notification confirms the capture.

### Tool-triggered capture

Ask Claude to take a screenshot -- it will invoke the `snip_screen` tool and open the overlay for you.

### Managing snips

These MCP tools are available to Claude:

| Tool | Description |
|------|-------------|
| `snip_screen` | Open the overlay and capture a region |
| `get_snip` | Retrieve a snip by name |
| `get_latest_snip` | Get the most recent capture |
| `list_snips` | List all stored snips |
| `rename_snip` | Rename a snip |
| `delete_snip` | Delete a snip |

## Configuration

Configuration is stored at `~/.snip_mcp/config.json` and auto-created on first run.

| Option | Default | Description |
|--------|---------|-------------|
| `modifier_keys` | `["ctrl", "shift"]` | Modifier keys held while clicking to trigger the overlay. Valid values: `ctrl`, `shift`, `alt` |
| `save_directory` | `~/.snip_mcp/snips/` | Directory where snip PNGs are stored |
| `overlay_alpha` | `0.3` | Overlay transparency (0.0 = invisible, 1.0 = opaque) |
| `selection_color` | `"#00ff00"` | Selection rectangle color (hex) |
| `selection_width` | `2` | Selection rectangle border width in pixels |
| `max_snips` | `50` | Maximum stored snips before oldest are auto-pruned |

Example config:

```json
{
  "modifier_keys": ["ctrl", "shift"],
  "save_directory": "C:/Users/you/.snip_mcp/snips",
  "overlay_alpha": 0.3,
  "selection_color": "#00ff00",
  "selection_width": 2,
  "max_snips": 50
}
```

## Troubleshooting

**"snip-mcp requires Windows"**
This server uses Windows-specific APIs (global mouse hooks via ctypes). It cannot run on macOS or Linux.

**"Failed to install mouse hook"**
The global mouse hook may require elevated permissions. Try running your terminal as administrator.

**Overlay doesn't appear**
Ensure no other application is intercepting Ctrl+Shift+Click. Verify `modifier_keys` in your config.

**Coordinates are offset on high-DPI displays**
The server calls `SetProcessDPIAware()` on startup. If you still see offset issues, check your Windows display scaling settings.

**Snips directory**
By default, snips are stored in `~/.snip_mcp/snips/`. You can change this in `config.json`.

## License

MIT -- see [LICENSE](LICENSE) for details.
