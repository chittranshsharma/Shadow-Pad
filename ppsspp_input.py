"""ShadowPad input verification: saved mappings, bounded holds, foreground checks."""

import configparser
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time


ACTIONS = ("Left", "Right", "Square", "Triangle", "Cross", "Circle")
MOVEMENT_ACTIONS = ("Left", "Right", "Up", "Down")
CONTROL_ACTIONS = MOVEMENT_ACTIONS + ("Square", "Triangle", "Cross", "Circle")
SPECIAL_KEYS = {19: (0x26, "Up"), 20: (0x28, "Down"),
                21: (0x25, "Left arrow"), 22: (0x27, "Right arrow"),
                62: (0x20, "Space"), 66: (0x0D, "Enter")}


def default_controls():
    """Find the existing Documents memory stick without hard-coding this user's name."""
    if sys.platform == "darwin":
        candidates = (Path.home() / ".config/ppsspp/PSP/SYSTEM/controls.ini",)
    else:
        candidates = (Path.home() / "OneDrive/Documents/PPSSPP/PSP/SYSTEM/controls.ini",
                      Path.home() / "Documents/PPSSPP/PSP/SYSTEM/controls.ini")
    return next((path for path in candidates if path.is_file()), candidates[0])


def read_bindings(path, actions=ACTIONS):
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(path, encoding="utf-8-sig") or not config.has_section("ControlMapping"):
        raise ValueError(f"PPSSPP controls file not found or invalid: {path}. Use --controls PATH.")
    bindings = {}
    # PPSSPP's Input/KeyCodes.h uses Android-style codes; device 1 is the keyboard.
    for action in actions:
        for mapping in config.get("ControlMapping", action, fallback="").split(","):
            parts = mapping.strip().split("-")
            if len(parts) != 2 or parts[0] != "1" or not parts[1].isdigit():
                continue
            code = int(parts[1])
            if 29 <= code <= 54:
                letter = chr(ord("A") + code - 29)
                bindings[action] = (ord(letter), letter)
                break
            if code in SPECIAL_KEYS:
                bindings[action] = SPECIAL_KEYS[code]
                break
        if action not in bindings:
            raise ValueError(f"{action} needs a supported keyboard binding in PPSSPP (letter or arrow).")
    return bindings


class BoundedTest:
    """One explicitly armed action; tick-based so focus loss interrupts a hold."""

    def __init__(self, backend):
        self.backend = backend
        self.state = "PAUSED"
        self.vk = None
        self.deadline = 0.0
        self.hold = 0.0
        self.target = None

    def arm(self, vk, delay, hold, now):
        if self.state not in ("PAUSED", "DONE", "CANCELLED"):
            raise ValueError("A test is already running.")
        if not 1 <= delay <= 10 or not 0.03 <= hold <= 1:
            raise ValueError("Delay must be 1-10 seconds; hold must be 0.03-1 second.")
        self.vk, self.hold = vk, hold
        self.deadline = now + delay
        self.target = None
        self.state = "COUNTDOWN"

    def tick(self, now):
        if self.state not in ("COUNTDOWN", "HOLDING"):
            return
        if self.backend.pause_requested():
            self.cancel()
            return
        if self.state == "COUNTDOWN" and now >= self.deadline:
            self.target = self.backend.foreground_ppsspp()
            if self.target is None:
                self.cancel()
                raise RuntimeError("Test cancelled: PPSSPP must be the active window when the countdown ends.")
            # Track HOLDING before the call so a partial/uncertain SendInput error still releases.
            self.state = "HOLDING"
            try:
                self.backend.press(self.vk, self.target)
            except BaseException:
                self.cancel()
                raise
            self.deadline = now + self.hold
        elif self.state == "HOLDING":
            if self.backend.foreground_ppsspp() != self.target:
                self.cancel()
            elif now >= self.deadline:
                self.backend.release()
                self.state = "DONE"

    def cancel(self):
        self.state = "CANCELLED"
        self.backend.release()


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", INPUTUNION)]


class PracticeKeyboard:
    """No native APIs: identical control decisions with no desktop key events."""

    is_practice = True

    def __init__(self):
        self.held = set()

    def foreground_ppsspp(self):
        return (0, 0)

    def pause_requested(self):
        return False

    def modifiers_down(self):
        return False

    def press(self, vk, target):
        self.held.add(vk)

    def release(self, vk=None):
        if vk is None:
            self.held.clear()
        else:
            self.held.discard(vk)


class WindowsKeyboard:
    def __init__(self):
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.held = {}
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        self.user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
        self.user32.MapVirtualKeyW.restype = wintypes.UINT
        self.user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self.user32.SendInput.restype = wintypes.UINT
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                          wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

    def foreground_ppsspp(self):
        window = self.user32.GetForegroundWindow()
        if not window:
            return None
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        process = self.kernel32.OpenProcess(0x1000, False, pid.value)
        if not process:
            return None
        try:
            length = wintypes.DWORD(32768)
            name = ctypes.create_unicode_buffer(length.value)
            if not self.kernel32.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(length)):
                return None
            if Path(name.value).name.casefold() in ("ppssppwindows.exe", "ppssppwindows64.exe"):
                return (int(window), pid.value)
        finally:
            self.kernel32.CloseHandle(process)
        return None

    def down(self, vk):
        return bool(self.user32.GetAsyncKeyState(vk) & 0x8000)

    def pause_requested(self):
        return self.down(0x11) and self.down(0x12) and self.down(ord("P"))

    def modifiers_down(self):
        return any(self.down(key) for key in (0x10, 0x11, 0x12, 0x5B, 0x5C))

    def _send(self, scan, extended, up=False):
        flags = 0x0008 | (0x0001 if extended else 0) | (0x0002 if up else 0)
        event = INPUT(type=1, data=INPUTUNION(ki=KEYBDINPUT(wScan=scan, dwFlags=flags)))
        if self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
            raise RuntimeError("Windows rejected keyboard input. Run PPSSPP and ShadowPad at the same privilege level.")

    def press(self, vk, target):
        if self.foreground_ppsspp() != target:
            raise RuntimeError("PPSSPP lost focus before key-down; test cancelled.")
        if self.down(vk) or self.modifiers_down():
            raise RuntimeError("Release keyboard keys and modifier keys, then retry.")
        scan = self.user32.MapVirtualKeyW(vk, 4)
        if not scan:
            raise RuntimeError("Cannot translate the configured key to a Windows scan code.")
        self.held[vk] = (scan & 0xFF, (scan >> 8) == 0xE0)
        self._send(*self.held[vk])

    def release(self, vk=None):
        errors = []
        for key in list(self.held) if vk is None else [vk]:
            if key not in self.held:
                continue
            try:
                self._send(*self.held[key], up=True)
            except Exception as error:
                errors.append(error)
            else:
                del self.held[key]
        if errors:
            raise errors[0]


# Quartz virtual key codes use physical US keyboard positions.
MAC_KEYCODES = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                        (0, 11, 8, 2, 14, 3, 5, 4, 34, 38, 40, 37, 46,
                         45, 31, 35, 12, 15, 1, 17, 32, 9, 13, 7, 16, 6)))
MAC_KEYCODES.update({0x25: 123, 0x27: 124, 0x28: 125, 0x26: 126,
                     0x20: 49, 0x0D: 36})


class MacKeyboard:
    """Quartz input gated by the frontmost PPSSPP app and Accessibility trust."""

    def __init__(self):
        if sys.platform != "darwin":
            raise RuntimeError("Mac keyboard input requires macOS.")
        from AppKit import NSWorkspace
        import Quartz

        services = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        services.AXIsProcessTrusted.restype = ctypes.c_bool
        if not services.AXIsProcessTrusted():
            raise RuntimeError("Grant Accessibility access to your Terminal/Python app in macOS System Settings, then restart ShadowPad.")
        self.workspace = NSWorkspace.sharedWorkspace()
        self.quartz = Quartz
        self.held = {}

    def foreground_ppsspp(self):
        app = self.workspace.frontmostApplication()
        if app is None or app.executableURL() is None:
            return None
        if str(app.executableURL().lastPathComponent()).casefold() in ("ppsspp", "ppssppsdl"):
            return app.processIdentifier()
        return None

    def down(self, code):
        return bool(self.quartz.CGEventSourceKeyState(self.quartz.kCGEventSourceStateHIDSystemState, code))

    def modifiers_down(self):
        q = self.quartz
        flags = q.CGEventSourceFlagsState(q.kCGEventSourceStateHIDSystemState)
        return bool(flags & (q.kCGEventFlagMaskShift | q.kCGEventFlagMaskControl |
                             q.kCGEventFlagMaskAlternate | q.kCGEventFlagMaskCommand))

    def pause_requested(self):
        q = self.quartz
        flags = q.CGEventSourceFlagsState(q.kCGEventSourceStateHIDSystemState)
        return bool(flags & q.kCGEventFlagMaskControl and flags & q.kCGEventFlagMaskAlternate
                    and self.down(MAC_KEYCODES["P"]))

    def _post(self, code, pressed):
        q = self.quartz
        event = q.CGEventCreateKeyboardEvent(None, code, pressed)
        if event is None:
            raise RuntimeError("macOS could not create a keyboard event.")
        q.CGEventPost(q.kCGHIDEventTap, event)

    def press(self, vk, target):
        if self.foreground_ppsspp() != target:
            raise RuntimeError("PPSSPP lost focus before key-down; input cancelled.")
        code = MAC_KEYCODES.get(chr(vk) if 65 <= vk <= 90 else vk)
        if code is None:
            raise ValueError("This PPSSPP keyboard binding has no macOS key mapping.")
        if self.down(code) or self.modifiers_down():
            raise RuntimeError("Release physical keys and modifiers, then retry.")
        self.held[vk] = code
        self._post(code, True)

    def release(self, vk=None):
        errors = []
        for key in list(self.held) if vk is None else [vk]:
            if key not in self.held:
                continue
            try:
                self._post(self.held[key], False)
            except Exception as error:
                errors.append(error)
            else:
                del self.held[key]
        if errors:
            raise errors[0]


def native_keyboard():
    if sys.platform == "win32":
        return WindowsKeyboard()
    if sys.platform == "darwin":
        return MacKeyboard()
    raise RuntimeError("Game input supports Windows and macOS only. Use --practice here.")


def execute_test(action, binding, delay=3, hold=0.12):
    backend = native_keyboard()
    test = BoundedTest(backend)
    print(f"ARMED: {action} -> {binding[1]}. Click PPSSPP within {delay:g} seconds.", flush=True)
    print("Hold Ctrl+Alt+P (Mac: Control+Option+P) to cancel. Each action automatically returns to paused.", flush=True)
    test.arm(binding[0], delay, hold, time.monotonic())
    try:
        while test.state in ("COUNTDOWN", "HOLDING"):
            test.tick(time.monotonic())
            time.sleep(0.01)
    finally:
        backend.release()
    print(f"{test.state}: keys released. Confirm the visible response in Tekken separately.", flush=True)
    return test.state
