"""OS-held per-user lock: duplicate launches cannot race durable capture queues."""
import os
from pathlib import Path


class InstanceLock:
    def __init__(self, directory):
        self.path = Path(directory) / 'desktop.instance.lock'
        self.stream = None
        self.mutex = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = open(self.path, 'a+b')
        if stream.seek(0, 2) == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            stream.close()
            return False
        self.stream = stream
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            from app_version import APP_MUTEX
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
            kernel.CreateMutexW.restype = wintypes.HANDLE
            self.mutex = kernel.CreateMutexW(None, False, APP_MUTEX)
            if not self.mutex:
                self.release()
                raise OSError('Could not register the running application')
        return True

    def release(self):
        if self.mutex:
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel.CloseHandle(self.mutex)
            self.mutex = None
        if self.stream:
            self.stream.close()
            self.stream = None
        # Never unlink: another process could hold the old inode while a third
        # opens a newly created file, bypassing the single-instance guarantee.
