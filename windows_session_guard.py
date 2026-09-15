"""Pause on Windows lock/disconnect/suspend; resume always requires the employee."""
import os
import threading
import uuid


def pause_reason(message, event):
    if message == 0x02B1:  # WM_WTSSESSION_CHANGE
        return {2: 'Windows session disconnected', 4: 'Remote session disconnected',
                6: 'Windows signed out', 7: 'Windows locked'}.get(event)
    if message == 0x0218 and event == 4:  # WM_POWERBROADCAST / PBT_APMSUSPEND
        return 'Windows is going to sleep'
    return None


class WindowsSessionGuard:
    def __init__(self, pause):
        self.pause = pause
        self.available = False
        self.closed = threading.Event()
        self.ready = threading.Event()
        self.hwnd = None
        self.thread = threading.Thread(target=self._run, daemon=True, name='WindowsSessionGuard')
        self.thread.start()

    def _run(self):
        if os.name != 'nt':
            self.ready.set()
            return
        import win32api
        import win32gui
        import win32ts
        name = 'DevTrackSessionGuard-' + uuid.uuid4().hex
        instance = win32api.GetModuleHandle(None)
        registered = False
        def procedure(hwnd, message, event, param):
            reason = pause_reason(message, event)
            if reason and not self.closed.is_set():
                self.pause(reason)
                return 1
            if message == 0x0010:  # WM_CLOSE
                win32gui.DestroyWindow(hwnd)
                return 0
            if message == 0x0002:  # WM_DESTROY
                win32gui.PostQuitMessage(0)
                return 0
            return win32gui.DefWindowProc(hwnd, message, event, param)
        try:
            window = win32gui.WNDCLASS()
            window.hInstance, window.lpszClassName, window.lpfnWndProc = instance, name, procedure
            win32gui.RegisterClass(window)
            # A hidden top-level window receives power broadcasts (a message-only
            # window would not receive all broadcast power notifications).
            self.hwnd = win32gui.CreateWindow(name, name, 0, 0, 0, 0, 0, 0, 0, instance, None)
            win32ts.WTSRegisterSessionNotification(self.hwnd, win32ts.NOTIFY_FOR_THIS_SESSION)
            registered = True
            self.available = True
            self.ready.set()
            if self.closed.is_set():
                win32gui.PostMessage(self.hwnd, 0x0010, 0, 0)
            win32gui.PumpMessages()
        except Exception:
            if not self.closed.is_set():
                self.pause('Windows lock/sleep protection became unavailable')
        finally:
            self.available = False
            self.ready.set()
            if registered:
                try:
                    win32ts.WTSUnRegisterSessionNotification(self.hwnd)
                except Exception:
                    pass
            try:
                if self.hwnd and win32gui.IsWindow(self.hwnd):
                    win32gui.DestroyWindow(self.hwnd)
                win32gui.UnregisterClass(name, instance)
            except Exception:
                pass
            self.hwnd = None

    def close(self):
        self.closed.set()
        if self.hwnd:
            try:
                import win32gui
                win32gui.PostMessage(self.hwnd, 0x0010, 0, 0)
            except Exception:
                pass
