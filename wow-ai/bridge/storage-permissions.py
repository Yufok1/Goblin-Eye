"""Protect the private runtime home with Windows ACLs; no third-party imports."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys


def protect(folder):
    if sys.platform != "win32":
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    security.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    security.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    security.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    security.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    security.GetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL)]
    security.SetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    security.SetNamedSecurityInfoW.restype = wintypes.DWORD
    token = wintypes.HANDLE()
    descriptor = ctypes.c_void_p()
    sid_text = wintypes.LPWSTR()

    def check(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())

    check(security.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)))
    try:
        size = wintypes.DWORD()
        security.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        user = ctypes.create_string_buffer(size.value)
        check(security.GetTokenInformation(token, 1, user, size, ctypes.byref(size)))
        sid = ctypes.cast(user, ctypes.POINTER(ctypes.c_void_p))[0]
        check(security.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)))
        # Inheritable access for the current account, SYSTEM and administrators.
        # No Authenticated Users/Users grant from the installation folder.
        acl = f"D:P(A;OICI;FA;;;{sid_text.value})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
        check(security.ConvertStringSecurityDescriptorToSecurityDescriptorW(acl, 1, ctypes.byref(descriptor), None))
        present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), ctypes.c_void_p()
        check(security.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)))
        error = security.SetNamedSecurityInfoW(str(Path(folder).resolve()), 1, 0x80000004, None, None, dacl, None)
        if error:
            raise ctypes.WinError(error)
    finally:
        if sid_text:
            kernel.LocalFree(ctypes.cast(sid_text, wintypes.HLOCAL))
        if descriptor:
            kernel.LocalFree(descriptor)
        kernel.CloseHandle(token)


if __name__ == "__main__":
    protect(sys.argv[1])
