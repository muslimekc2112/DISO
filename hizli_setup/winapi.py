"""The few Windows facilities the installer needs, through ctypes (no extra package):
well-known folders, shortcuts, finding / closing the running program, delayed delete."""
import ctypes
import os
import sys
import time
from ctypes import POINTER, WINFUNCTYPE, Structure, byref, c_void_p, wintypes

WINDOWS = sys.platform.startswith("win")

# folder ids (KNOWNFOLDERID)
FOLDER_PROGRAMS = "{A77F5D77-2E2B-44C3-A6A2-ABA601054A51}"          # Start Menu\\Programs of this user
FOLDER_DESKTOP = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"           # follows OneDrive / a moved desktop
FOLDER_LOCAL_APPDATA = "{F1B32785-6FBA-4FCF-9D55-7B8E7F157091}"
FOLDER_COMMON_PROGRAMS = "{0139D44E-6AFE-49F2-8690-3DAFCAE6FFB8}"       # the Start Menu for every user
FOLDER_PUBLIC_DESKTOP = "{C4AA340D-F20F-4863-AFEF-F87EF2E6BA25}"        # the desktop shared by every user
FOLDER_PROGRAM_FILES = "{6D809377-6AF0-444B-8957-A3773F02200E}"         # C:\\Program Files (64-bit)

_CLSID_SHELLLINK = "{00021401-0000-0000-C000-000000000046}"
_IID_SHELLLINKW = "{000214F9-0000-0000-C000-000000000046}"
_IID_PERSISTFILE = "{0000010B-0000-0000-C000-000000000046}"
_COINIT_APARTMENTTHREADED = 0x2
_CLSCTX_INPROC_SERVER = 0x1
_WM_CLOSE = 0x0010
_PROCESS_TERMINATE = 0x0001
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TH32CS_SNAPPROCESS = 0x2
_MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
_STGM_READ = 0


class GUID(Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]


class _PROCESSENTRY32W(Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260)]


def _guid(text) -> GUID:
    g = GUID()
    ole32 = ctypes.OleDLL("ole32")
    ole32.CLSIDFromString(text, byref(g))
    return g


def _method(obj, index, *argtypes):
    """Call a COM method by its position in the object's vtable (returns an HRESULT-checked callable)."""
    vtable = ctypes.cast(ctypes.cast(obj, POINTER(c_void_p))[0], POINTER(c_void_p))
    return WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)(vtable[index])


def _release(obj):
    if obj and obj.value:
        WINFUNCTYPE(ctypes.c_ulong, c_void_p)(ctypes.cast(ctypes.cast(obj, POINTER(c_void_p))[0], POINTER(c_void_p))[2])(obj)


# ----------------------------------------------------------------------------------- folders
def known_folder(folder_id: str) -> str:
    """The real path of a well-known folder of the current user."""
    if not WINDOWS:
        raise OSError("Windows only")
    shell32 = ctypes.windll.shell32
    shell32.SHGetKnownFolderPath.argtypes = [POINTER(GUID), wintypes.DWORD, wintypes.HANDLE, POINTER(ctypes.c_wchar_p)]
    shell32.SHGetKnownFolderPath.restype = ctypes.HRESULT
    ctypes.windll.ole32.CoTaskMemFree.argtypes = [c_void_p]
    out = ctypes.c_wchar_p()
    shell32.SHGetKnownFolderPath(byref(_guid(folder_id)), 0, None, byref(out))
    try:
        return out.value
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)


# ----------------------------------------------------------------------------------- shortcuts
class _ComScope:
    """CoInitialize for the duration of a with-block (the thread may already have done it)."""

    def __enter__(self):
        self.owned = ctypes.windll.ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED) in (0, 1)
        return self

    def __exit__(self, *a):
        if self.owned:
            ctypes.windll.ole32.CoUninitialize()


def _shell_link():
    ole32 = ctypes.OleDLL("ole32")
    link = c_void_p()
    ole32.CoCreateInstance(byref(_guid(_CLSID_SHELLLINK)), None, _CLSCTX_INPROC_SERVER,
                           byref(_guid(_IID_SHELLLINKW)), byref(link))
    persist = c_void_p()
    _method(link, 0, c_void_p, c_void_p)(link, byref(_guid(_IID_PERSISTFILE)), byref(persist))
    return link, persist


def create_shortcut(path, target, arguments="", workdir="", description="", icon="", icon_index=0):
    """Write a .lnk file. The folder of `path` is created."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _ComScope():
        link, persist = _shell_link()
        try:
            _method(link, 20, wintypes.LPCWSTR)(link, target)                          # SetPath
            if arguments:
                _method(link, 11, wintypes.LPCWSTR)(link, arguments)                   # SetArguments
            if workdir:
                _method(link, 9, wintypes.LPCWSTR)(link, workdir)                      # SetWorkingDirectory
            if description:
                _method(link, 7, wintypes.LPCWSTR)(link, description)                  # SetDescription
            if icon:
                _method(link, 17, wintypes.LPCWSTR, ctypes.c_int)(link, icon, icon_index)   # SetIconLocation
            _method(persist, 6, wintypes.LPCWSTR, wintypes.BOOL)(persist, path, True)  # Save
        finally:
            _release(persist)
            _release(link)


def read_shortcut(path) -> dict:
    """{"target", "arguments", "workdir", "description"} of a .lnk file (used to check what we wrote
    and to make sure a shortcut still points at us before it is deleted)."""
    with _ComScope():
        link, persist = _shell_link()
        try:
            _method(persist, 5, wintypes.LPCWSTR, wintypes.DWORD)(persist, path, _STGM_READ)    # Load
            buf = ctypes.create_unicode_buffer(1024)
            out = {}
            data = ctypes.create_string_buffer(592)                                              # WIN32_FIND_DATAW
            _method(link, 3, wintypes.LPWSTR, ctypes.c_int, c_void_p, wintypes.DWORD)(link, buf, 1024, data, 0)
            out["target"] = buf.value
            _method(link, 10, wintypes.LPWSTR, ctypes.c_int)(link, buf, 1024)
            out["arguments"] = buf.value
            _method(link, 8, wintypes.LPWSTR, ctypes.c_int)(link, buf, 1024)
            out["workdir"] = buf.value
            _method(link, 6, wintypes.LPWSTR, ctypes.c_int)(link, buf, 1024)
            out["description"] = buf.value
            return out
        finally:
            _release(persist)
            _release(link)


# ----------------------------------------------------------------------------------- processes
def _snapshot():
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = [wintypes.HANDLE, POINTER(_PROCESSENTRY32W)]
    k32.Process32NextW.argtypes = [wintypes.HANDLE, POINTER(_PROCESSENTRY32W)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = k32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    entries = []
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = k32.Process32FirstW(snap, byref(entry))
        while ok:
            entries.append((entry.th32ProcessID, entry.th32ParentProcessID))
            ok = k32.Process32NextW(snap, byref(entry))
    finally:
        k32.CloseHandle(snap)
    return entries


def _image_path(pid):
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        return buf.value if k32.QueryFullProcessImageNameW(handle, 0, buf, byref(size)) else ""
    finally:
        k32.CloseHandle(handle)


def processes_in(folder, ignore_names=()):
    """[(pid, parent_pid, exe path)] of the running programs whose file lives inside `folder`
    (except those whose file name, in lower case, is in ignore_names)."""
    if not WINDOWS or not folder:
        return []
    ignore = {n.lower() for n in ignore_names}
    prefix = os.path.normcase(os.path.abspath(folder)).rstrip("\\/") + os.sep
    me = os.getpid()
    out = []
    for pid, parent in _snapshot():
        if pid == me:
            continue
        path = _image_path(pid)
        if path and os.path.normcase(os.path.abspath(path)).startswith(prefix) and os.path.basename(path).lower() not in ignore:
            out.append((pid, parent, path))
    return out


def _post_close(pids):
    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, POINTER(wintypes.DWORD)]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    sent = []

    @WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, byref(pid))
        if pid.value in pids:
            user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)
            sent.append(hwnd)
        return True

    user32.EnumWindows.argtypes = [WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
    user32.EnumWindows(each, 0)
    return len(sent)


def _terminate(pid):
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k32.OpenProcess(_PROCESS_TERMINATE, False, pid)
    if handle:
        try:
            k32.TerminateProcess(handle, 1)
        finally:
            k32.CloseHandle(handle)


def close_programs_in(folder, grace=8.0, poll=0.25, sleep=time.sleep, now=time.time, ignore_names=()):
    """Ask the programs that run from `folder` to close (as if their window's X was pressed), wait,
    then end what is left. A one-file program is two processes (a launcher and the real one): the
    real one is ended first so the launcher can clean up its temporary files by itself.
    Returns the number of processes that had to be ended by force."""
    def here():
        return processes_in(folder, ignore_names)

    found = here()
    if not found:
        return 0
    _post_close({pid for pid, _, _ in found})
    deadline = now() + grace
    while now() < deadline and here():
        sleep(poll)
    left = here()
    if not left:
        return 0
    parents = {parent for _, parent, _ in left}
    for pid, _, _ in left:
        if pid not in parents:                       # the innermost first
            _terminate(pid)
    end = now() + 5.0
    while now() < end and here() and any(p not in parents for p, _, _ in here()):
        sleep(poll)
    survivors = here()
    deadline = now() + 4.0                           # the launcher usually leaves by itself now
    while survivors and now() < deadline:
        sleep(poll)
        survivors = here()
    for pid, _, _ in survivors:
        _terminate(pid)
    sleep(poll)
    return len(left)


# ----------------------------------------------------------------------------------- misc
def delete_on_reboot(path) -> bool:
    """Ask Windows to delete a file that is in use the next time it starts."""
    if not WINDOWS:
        return False
    k32 = ctypes.windll.kernel32
    k32.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    return bool(k32.MoveFileExW(path, None, _MOVEFILE_DELAY_UNTIL_REBOOT))


def wait_for_exit(pid, timeout=60.0) -> bool:
    """Wait until a process has ended. True if it has (or never existed), False after the timeout."""
    if not WINDOWS or not pid:
        return True
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k32.OpenProcess(0x00100000, False, pid)             # SYNCHRONIZE
    if not handle:
        return True                                              # gone already, or not ours to wait for
    try:
        return k32.WaitForSingleObject(handle, int(timeout * 1000)) == 0
    finally:
        k32.CloseHandle(handle)


def single_instance(name):
    """Hold a named lock so that a second copy of the installer can tell it is not alone.
    Returns a handle to keep alive, or None when another copy already holds the lock."""
    if not WINDOWS:
        return object()
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateMutexW.argtypes = [c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    handle = k32.CreateMutexW(None, False, name)
    if ctypes.get_last_error() == 183:                       # ERROR_ALREADY_EXISTS
        release_instance(handle)                             # we got a second handle to the same lock: give it back
        return None
    return handle or None


def release_instance(handle):
    """Let go of the lock taken by single_instance (the system does it too when the program ends)."""
    if WINDOWS and isinstance(handle, int) and handle:
        k32 = ctypes.windll.kernel32
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle(handle)


class _SHELLEXECUTEINFOW(Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG), ("hwnd", wintypes.HWND),
                ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                ("lpIDList", c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]


def is_admin() -> bool:
    """True when this process runs with administrator rights."""
    if not WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def run_elevated(exe, parameters="", wait=False):
    """Start a program with administrator rights (Windows asks the user to allow it).
    Returns (started, exit_code): started is False if the user said no; exit_code is only known when
    wait=True (None otherwise)."""
    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    # SEE_MASK_NOCLOSEPROCESS (keep the handle to wait on) | SEE_MASK_FLAG_NO_UI (no error box of Windows' own:
    # a program that cannot be started is reported by us, not by a window that waits for a click)
    info.fMask = 0x40 | 0x400
    info.lpVerb = "runas"
    info.lpFile = exe
    info.lpParameters = parameters or None
    info.lpDirectory = os.path.dirname(exe) or None
    info.nShow = 1
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [POINTER(_SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    if not shell32.ShellExecuteExW(byref(info)):
        return False, None                                          # 1223 = the user cancelled the question
    code = None
    k32 = ctypes.windll.kernel32
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    if wait and info.hProcess:
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, POINTER(wintypes.DWORD)]
        k32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
        out = wintypes.DWORD()
        k32.GetExitCodeProcess(info.hProcess, byref(out))
        code = out.value
    if info.hProcess:
        k32.CloseHandle(info.hProcess)
    return True, code


def launch_unelevated(exe) -> bool:
    """Start a program as the normal user even when we are running as administrator (a program the
    installer opens at the end must not run with administrator rights). The shell does it for us."""
    import subprocess
    try:
        if is_admin():
            subprocess.Popen(["explorer.exe", exe], close_fds=True, creationflags=0x00000008)
        else:
            subprocess.Popen([exe], cwd=os.path.dirname(exe), close_fds=True, creationflags=0x00000008 | 0x00000200,
                             env=dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1"),
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def free_space(path) -> int:
    """Free bytes on the drive that holds `path` (the nearest folder that exists is asked)."""
    probe = os.path.abspath(path)
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    import shutil
    return shutil.disk_usage(probe).free
