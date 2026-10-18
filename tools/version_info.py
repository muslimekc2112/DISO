"""The 'Details' tab of a program's properties (company, description, version), made for PyInstaller."""
import os
import re

COMPANY = "ISO"                      # the publisher: also the folder under Program Files
PRODUCT = "DISO"


def version_tuple(version):
    parts = [int(p) for p in re.findall(r"\d+", version)][:4]
    return tuple(parts + [0] * (4 - len(parts)))


def version_file_text(description, filename, version, label=None):
    v = version_tuple(version)
    shown = ".".join(str(n) for n in v)
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{COMPANY}'),
      StringStruct('FileDescription', '{description}'),
      StringStruct('FileVersion', '{shown}'),
      StringStruct('InternalName', '{filename}'),
      StringStruct('OriginalFilename', '{filename}'),
      StringStruct('ProductName', '{PRODUCT}'),
      StringStruct('ProductVersion', '{label or shown}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
"""


def write_version_file(path, description, filename, version, label=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(version_file_text(description, filename, version, label))
    return path
