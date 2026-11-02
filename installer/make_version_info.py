"""Writes installer/version_info.txt (the version details Windows shows in the exe's Properties) for PyInstaller.

FileDescription and ProductName are the shown name (Task Manager, Properties). InternalName and OriginalFilename
stay SC Shard Status, matching the exe's file name, which never changes."""
import sys
from pathlib import Path

ver = sys.argv[1]
n = (list(map(int, ver.split("."))) + [0, 0, 0, 0])[:4]
t = tuple(n)
Path(__file__).with_name("version_info.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Aurelius_Draco'),
      StringStruct('FileDescription', 'Verse Shards for PC'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'SC Shard Status'),
      StringStruct('LegalCopyright', 'MIT licence. Fan made, not affiliated with Cloud Imperium Games.'),
      StringStruct('OriginalFilename', 'SC Shard Status.exe'),
      StringStruct('ProductName', 'Verse Shards for PC'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")
print("version_info.txt for", ver)
