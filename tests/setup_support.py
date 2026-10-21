"""Shared by the installer tests: a pretend setup package and a stand-in for 'close the program'."""
import hashlib
import json


def make_payload(folder, version="1.2.0", extra=(), seed=b"a", program_folder=False):
    """A pretend setup package: three files and payload.json with their checksums. program_folder: like the real
    one, DISO.exe with its _internal/ folder and no Uninstall.exe (DISO.exe --uninstall removes DISO)."""
    folder.mkdir(parents=True, exist_ok=True)
    contents = {"DISO.exe": seed * 300_000, "Uninstall.exe": seed * 20_000, "deno.exe": seed * 50_000}
    layout = {"DISO.exe": "DISO.exe", "Uninstall.exe": "Uninstall.exe", "deno.exe": "deno/deno.exe"}
    if program_folder:
        del contents["Uninstall.exe"], layout["Uninstall.exe"]
        for name in ("app/_internal/python315.dll", "app/_internal/ffmpeg/ffmpeg.exe"):
            contents[name] = seed * 4000
            layout[name] = name[len("app/"):]
    for name in extra:
        contents[name] = b"extra-" + seed * 1000
        layout[name] = name
    files = []
    for name, data in contents.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
        files.append({"name": name, "dest": layout[name], "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
    (folder / "payload.json").write_text(json.dumps({"version": version, "files": files}), encoding="utf-8")
    return folder


class Closer:
    """Records which folders the installer asked to be cleared of running programs."""

    def __init__(self):
        self.calls = []

    def __call__(self, folder):
        self.calls.append(folder)
        return 0
