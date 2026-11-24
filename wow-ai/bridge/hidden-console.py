"""Run a CLI and its native descendants on a private background desktop.

CREATE_NO_WINDOW on the outer process alone is insufficient: native CLI helpers
can allocate visible consoles when they have no console to inherit, or explicitly
request new windows. The private desktop contains both cases without switching
the user's input desktop.
No shell is used; stdin/stdout/stderr remain the bridge's protocol pipes.
"""
import os
import subprocess
import sys
import ctypes
import msvcrt
from ctypes import wintypes
from contextlib import contextmanager
from uuid import uuid4


@contextmanager
def background_desktop():
    """Keep even helpers that explicitly create/show windows off the input desktop.

    This never switches the user's desktop. Descendants inherit this thread's
    desktop; pipe I/O, credentials, filesystem and network access are unchanged.
    Fail closed if Windows cannot create it rather than launch visibly.
    """
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.CreateDesktopW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p,
                                     ctypes.c_void_p, wintypes.DWORD,
                                     wintypes.DWORD, ctypes.c_void_p]
    user32.CreateDesktopW.restype = wintypes.HANDLE
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.CloseDesktop.restype = wintypes.BOOL
    name = 'GoblinEye-' + uuid4().hex
    desktop = user32.CreateDesktopW(name, None, None, 0, 0x01FF, None)
    if not desktop:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield name
    finally:
        user32.CloseDesktop(desktop)


class StartupInfo(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('reserved', wintypes.LPWSTR),
                ('desktop', wintypes.LPWSTR), ('title', wintypes.LPWSTR),
                *[(key, wintypes.DWORD) for key in
                  ('x', 'y', 'xSize', 'ySize', 'xChars', 'yChars', 'fill', 'flags')],
                ('show', wintypes.WORD), ('reservedSize', wintypes.WORD),
                ('reservedBytes', ctypes.c_void_p),
                ('stdin', wintypes.HANDLE), ('stdout', wintypes.HANDLE),
                ('stderr', wintypes.HANDLE)]


class ProcessInfo(ctypes.Structure):
    _fields_ = [('process', wintypes.HANDLE), ('thread', wintypes.HANDLE),
                ('pid', wintypes.DWORD), ('tid', wintypes.DWORD)]


class JobLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                ('flags', wintypes.DWORD), ('min_working_set', ctypes.c_size_t),
                ('max_working_set', ctypes.c_size_t), ('active_processes', wintypes.DWORD),
                ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                ('scheduling', wintypes.DWORD)]


class ExtendedJobLimits(ctypes.Structure):
    _fields_ = [('basic', JobLimits), ('io_counters', ctypes.c_uint64 * 6),
                ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]


def run_on_desktop(command, desktop):
    # Python's subprocess STARTUPINFO does not expose lpDesktop. Pass it
    # explicitly to CreateProcessW; changing only our thread desktop is not
    # sufficient to select the child's desktop.
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
        ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(StartupInfo),
        ctypes.POINTER(ProcessInfo)]
    kernel.CreateProcessW.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedJobLimits()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel.CloseHandle(job)
        raise error
    startup = StartupInfo()
    startup.cb = ctypes.sizeof(startup)
    startup.desktop = desktop
    startup.flags = subprocess.STARTF_USESTDHANDLES | subprocess.STARTF_USESHOWWINDOW
    startup.show = subprocess.SW_HIDE
    descriptors = []
    info = ProcessInfo()
    try:
        for field, stream in [('stdin', sys.stdin), ('stdout', sys.stdout), ('stderr', sys.stderr)]:
            fd = os.dup(stream.fileno())
            descriptors.append(fd)
            handle = msvcrt.get_osfhandle(fd)
            os.set_handle_inheritable(handle, True)
            setattr(startup, field, handle)
        line = ctypes.create_unicode_buffer(subprocess.list2cmdline(command))
        if not kernel.CreateProcessW(None, line, None, None, True,
                                     subprocess.CREATE_NEW_CONSOLE | 0x4, None, None,
                                     ctypes.byref(startup), ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        # Assign before the child can spawn helpers. Closing this wrapper's job
        # handle then stops every descendant, even if the wrapper is terminated.
        if not kernel.AssignProcessToJobObject(job, info.process):
            raise ctypes.WinError(ctypes.get_last_error())
        if kernel.ResumeThread(info.thread) == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
    except BaseException:
        if info.process:
            kernel.TerminateProcess(info.process, 1)
        kernel.CloseHandle(job)
        if info.thread:
            kernel.CloseHandle(info.thread)
        if info.process:
            kernel.CloseHandle(info.process)
        raise
    finally:
        for fd in descriptors:
            os.close(fd)
    try:
        if kernel.WaitForSingleObject(info.process, 0xFFFFFFFF) == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        status = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(info.process, ctypes.byref(status)):
            raise ctypes.WinError(ctypes.get_last_error())
        return status.value
    finally:
        kernel.CloseHandle(info.thread)
        kernel.CloseHandle(info.process)
        kernel.CloseHandle(job)


def main():
    os.environ['GOBLIN_EYE_HIDDEN_CONSOLE'] = '1'
    with background_desktop() as desktop:
        return run_on_desktop(sys.argv[1:], desktop)


if __name__ == "__main__":
    sys.exit(main())
