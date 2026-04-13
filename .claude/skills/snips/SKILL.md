---
name: snips
description: List and manage screen capture snips - view, rename, or delete captured screenshots
---

# Snips Manager

List and manage captured screen snips.

## Steps

1. Call the `mcp__snip__list_snips` tool to show all captured snips with their names and timestamps.
2. Present the list to the user in a clear format.
3. Ask the user what they'd like to do:
   - **View a snip**: Call `mcp__snip__get_snip` with the snip name
   - **Rename a snip**: Call `mcp__snip__rename_snip` with old and new names
   - **Delete a snip**: Call `mcp__snip__delete_snip` with the snip name
   - **Capture new**: Call `mcp__snip__snip_screen` to take a new screenshot
4. If the user provides arguments (e.g., `/snips rename snip_1 my_design`), execute that action directly without listing first.
