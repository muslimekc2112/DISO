"""Run a command (the tests) on a desktop of its own that nobody sees: the windows the tests open never come up on
the screen of whoever is working at the computer, and never take the keyboard from them.

    python tools/run_hidden.py [--out FILE] -- python -m pytest tests -q

Windows only. The command's output goes to FILE (default: run_hidden.log next to this file) and is printed
when it ends; the exit code is the command's."""
import ctypes
import os
import subprocess
import sys
from ctypes import wintypes

DESKTOP = "DISO-tests-big"
GENERIC_ALL = 0x10000000
INFINITE = 0xFFFFFFFF
HEAP_KB = 65536


class STARTUPINFO(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD), ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE), ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD)]


def run(command, out):
    user32, kernel32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
    user32.CreateDesktopExW.restype = wintypes.HANDLE
    # a desktop's own memory for windows (KB): the tests open and close hundreds of them; Windows' default for a
    # new desktop ran out near the end of the suite ("access violation")
    desk = user32.CreateDesktopExW(DESKTOP, None, None, 0, GENERIC_ALL, None, HEAP_KB, None)
    if not desk:
        raise OSError(ctypes.get_last_error(), "CreateDesktop failed")
    try:
        # the output through cmd: the new desktop has no console of ours
        line = f'cmd /c "{subprocess.list2cmdline(command)} > "{out}" 2>&1"'
        si = STARTUPINFO()
        si.cb = ctypes.sizeof(si)
        si.lpDesktop = f"WinSta0\\{DESKTOP}"
        pi = PROCESS_INFORMATION()
        flags = 0x08000000                                    # CREATE_NO_WINDOW
        if not kernel32.CreateProcessW(None, ctypes.create_unicode_buffer(line), None, None, False, flags, None,
                                       os.getcwd(), ctypes.byref(si), ctypes.byref(pi)):
            raise OSError(ctypes.get_last_error(), "CreateProcess failed")
        kernel32.WaitForSingleObject(pi.hProcess, INFINITE)
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
        kernel32.CloseHandle(pi.hThread)
        kernel32.CloseHandle(pi.hProcess)
        return code.value
    finally:
        user32.CloseDesktop(desk)


def main(argv):
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_hidden.log")
    if argv[:1] == ["--out"]:
        out, argv = os.path.abspath(argv[1]), argv[2:]
    if argv[:1] == ["--"]:
        argv = argv[1:]
    if not argv:
        print(__doc__)
        return 2
    code = run(argv, out)
    with open(out, encoding="utf-8", errors="replace") as f:
        sys.stdout.write(f.read())
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
