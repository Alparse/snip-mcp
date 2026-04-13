"""Global input listener + tkinter overlay for screen snipping.

Uses a low-level mouse hook (WH_MOUSE_LL) + GetAsyncKeyState to detect
Ctrl+Shift+LeftClick. When detected, shows a transparent overlay. The overlay
uses native tkinter mouse bindings for click-drag-release selection.

Hook only does: detect trigger -> show overlay.
Tkinter does: click-drag-release -> rectangle -> coordinates.

Interaction:
  Ctrl+Shift + Left-click  -> overlay appears (hook)
  Click + drag on overlay  -> green rectangle stretches (tkinter)
  Release on overlay       -> capture coords, hide overlay (tkinter)
  Escape                   -> cancel
"""

import sys

if sys.platform != "win32":
    sys.exit("snip-mcp listener requires Windows (uses ctypes global mouse hooks)")

import ctypes
import ctypes.wintypes
import json
import queue
import threading
import tkinter as tk

# --- Windows constants ---
WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
VK_CONTROL = 0x11
VK_SHIFT = 0x10

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

HOOKPROC = ctypes.CFUNCTYPE(
    ctypes.c_long,
    ctypes.c_int,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
)

user32 = ctypes.WinDLL("user32", use_last_error=True)

user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]


def is_key_down(vk: int) -> bool:
    return (user32.GetAsyncKeyState(vk) & 0x8000) != 0


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", ctypes.wintypes.POINT),
        ("mouseData", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class SnipListener:
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.overlay_alpha = config.get("overlay_alpha", 0.3)
        self.selection_color = config.get("selection_color", "#00ff00")
        self.selection_width = config.get("selection_width", 2)

        self.snipping = False
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None

        # Queue for hook -> tkinter communication (only "show overlay" events)
        self._show_queue = queue.Queue()

        # Virtual screen bounds
        self.vscreen_x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        self.vscreen_y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        self.vscreen_w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        self.vscreen_h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

        self._mouse_hook = None
        self._mouse_proc = None
        self._overlay_visible = False

        self.root = tk.Tk()
        self.root.withdraw()
        self._setup_overlay()

    def _setup_overlay(self):
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.overlay_alpha)
        self.root.configure(background="black")
        self.root.geometry(
            f"{self.vscreen_w}x{self.vscreen_h}"
            f"+{self.vscreen_x}+{self.vscreen_y}"
        )
        self.canvas = tk.Canvas(
            self.root, bg="black", highlightthickness=0, cursor="crosshair",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Native tkinter mouse bindings for selection
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Escape>", lambda e: self._cancel_snip())

    def _on_press(self, event):
        """Left button pressed on overlay canvas -- start rectangle."""
        self.snipping = True
        # Canvas coords -> screen coords
        self.start_x = event.x + self.vscreen_x
        self.start_y = event.y + self.vscreen_y
        self.canvas.delete("all")
        self.rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline=self.selection_color, width=self.selection_width,
        )

    def _on_drag(self, event):
        """Mouse dragged with left button held -- update rectangle."""
        if self.rect_id is None:
            return
        sx = self.start_x - self.vscreen_x
        sy = self.start_y - self.vscreen_y
        self.canvas.coords(self.rect_id, sx, sy, event.x, event.y)

    def _on_release(self, event):
        """Left button released -- confirm snip."""
        if not self.snipping:
            return
        self.snipping = False
        self._overlay_visible = False
        self.root.withdraw()

        end_x = event.x + self.vscreen_x
        end_y = event.y + self.vscreen_y

        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)
        w = x2 - x1
        h = y2 - y1

        if w < 10 or h < 10:
            result = {"cancelled": True, "reason": "selection_too_small"}
        else:
            result = {"x": x1, "y": y1, "width": w, "height": h, "cancelled": False}

        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()
        self.rect_id = None

    def _cancel_snip(self):
        self.snipping = False
        self._overlay_visible = False
        self.root.withdraw()
        self.rect_id = None
        sys.stdout.write(json.dumps({"cancelled": True, "reason": "user_cancelled"}) + "\n")
        sys.stdout.flush()

    def _show_overlay(self):
        """Show the overlay for snipping."""
        if self._overlay_visible:
            return
        self._overlay_visible = True
        self.canvas.delete("all")
        self.rect_id = None
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    # --- Hook: only watches for Ctrl+Shift+Click to show overlay ---

    def _install_hooks(self):
        self._mouse_proc = HOOKPROC(self._mouse_hook_proc)
        self._mouse_hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._mouse_proc, None, 0,
        )
        if not self._mouse_hook:
            err = ctypes.get_last_error()
            raise RuntimeError(f"Failed to install mouse hook (error {err})")

    def _mouse_hook_proc(self, nCode, wParam, lParam):
        if nCode >= 0 and wParam == WM_LBUTTONDOWN:
            if not self._overlay_visible:
                ctrl = is_key_down(VK_CONTROL)
                shift = is_key_down(VK_SHIFT)
                if ctrl and shift:
                    self._show_queue.put(("show", None))
        return user32.CallNextHookEx(self._mouse_hook, nCode, wParam, lParam)

    def _poll_show_queue(self):
        """Check if the hook wants to show the overlay or a toast."""
        try:
            while True:
                action, data = self._show_queue.get_nowait()
                if action == "show":
                    self._show_overlay()
                elif action == "toast":
                    self._show_toast(data)
        except queue.Empty:
            pass
        self.root.after(16, self._poll_show_queue)

    def _show_toast(self, message: str):
        """Show a brief notification popup in the bottom-right corner."""
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.attributes("-alpha", 0.9)
        toast.configure(background="#1a1a2e")

        frame = tk.Frame(toast, bg="#1a1a2e", padx=16, pady=10)
        frame.pack()

        tk.Label(
            frame, text=message, fg="#00ff00", bg="#1a1a2e",
            font=("Consolas", 12, "bold"),
        ).pack()

        # Position bottom-right of primary monitor
        toast.update_idletasks()
        w = toast.winfo_reqwidth()
        h = toast.winfo_reqheight()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        toast.geometry(f"+{screen_w - w - 20}+{screen_h - h - 60}")

        # Auto-dismiss after 2.5 seconds
        toast.after(2500, toast.destroy)

    # --- Stdin reader for tool-triggered activation ---

    def _start_stdin_reader(self):
        def reader():
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    cmd = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if cmd.get("activate"):
                    self._show_queue.put(("show", None))
                elif cmd.get("toast"):
                    self._show_queue.put(("toast", cmd["toast"]))
                elif cmd.get("shutdown"):
                    self.root.after(0, self.root.quit)
        threading.Thread(target=reader, daemon=True).start()

    def _cleanup_hooks(self):
        if self._mouse_hook:
            user32.UnhookWindowsHookEx(self._mouse_hook)

    def run(self):
        self._install_hooks()
        self._start_stdin_reader()
        self.root.after(16, self._poll_show_queue)
        try:
            sys.stdout.write(json.dumps({"ready": True}) + "\n")
            sys.stdout.flush()
            self.root.mainloop()
        finally:
            self._cleanup_hooks()


def main():
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

    config = {}
    if len(sys.argv) > 1:
        try:
            config = json.loads(sys.argv[1])
        except (json.JSONDecodeError, IndexError):
            pass

    SnipListener(config).run()


if __name__ == "__main__":
    main()
