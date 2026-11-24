"""Regression fixture: a helper explicitly requests its own visible console."""
import ctypes
from ctypes import wintypes
import json
import subprocess
import sys

user = ctypes.WinDLL('user32', use_last_error=True)
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
user.GetThreadDesktop.argtypes = [wintypes.DWORD]
user.GetThreadDesktop.restype = wintypes.HANDLE
user.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user.OpenInputDesktop.restype = wintypes.HANDLE
user.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                         ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.POINTER(wintypes.DWORD)]
user.CloseDesktop.argtypes = [wintypes.HANDLE]


def name(handle):
    buf = ctypes.create_unicode_buffer(256)
    needed = wintypes.DWORD()
    if not user.GetUserObjectInformationW(handle, 2, buf, ctypes.sizeof(buf), ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    return buf.value


desktop = name(user.GetThreadDesktop(kernel.GetCurrentThreadId()))
input_handle = user.OpenInputDesktop(0, False, 1)
if not input_handle:
    raise ctypes.WinError(ctypes.get_last_error())
try:
    assert desktop != name(input_handle), 'helper must not use the visible input desktop'
    assert desktop.startswith('GoblinEye-')
finally:
    user.CloseDesktop(input_handle)

if '--assert-only' in sys.argv:
    sys.exit(0)

if '--wait' in sys.argv:
    import os
    import time
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
    print(json.dumps({'parent': os.getpid(), 'child': child.pid}), flush=True)
    time.sleep(60)
    sys.exit(0)

if '--watch-wrapper' in sys.argv:
    wrapper = subprocess.Popen([sys.executable, '-I', sys.argv[2], sys.executable, __file__, '--wait'],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    handles = []
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    try:
        pids = json.loads(wrapper.stdout.readline())
        for pid in pids.values():
            handle = kernel.OpenProcess(0x100000, False, pid)
            assert handle, 'child must be running before wrapper termination'
            handles.append(handle)
        wrapper.terminate()
        wrapper.communicate(timeout=5)
        for handle in handles:
            assert kernel.WaitForSingleObject(handle, 5000) == 0, 'orphan helper survived wrapper termination'
        print('wrapper termination stopped the complete helper tree')
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
        for handle in handles:
            kernel.CloseHandle(handle)
    sys.exit(0)

if '--child' in sys.argv:
    # Only show after verifying isolation: this cannot flash on the user's desktop.
    kernel.GetConsoleWindow.restype = wintypes.HWND
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.ShowWindow(kernel.GetConsoleWindow(), 5)
    print(json.dumps({'desktop': desktop, 'input': sys.stdin.read()}))
    sys.stderr.write('stderr intact')
    sys.exit(7)

result = subprocess.run([sys.executable, __file__, '--child'],
                        creationflags=subprocess.CREATE_NEW_CONSOLE,
                        input='literal pipe data', capture_output=True, text=True)
assert result.returncode == 7, result.stderr
assert json.loads(result.stdout) == {'desktop': desktop, 'input': 'literal pipe data'}
assert result.stderr == 'stderr intact'
print('isolated native child; stdin, stdout, stderr and exit status intact')
