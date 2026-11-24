from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
import shutil

BEFORE = "930d00d79986bdf992238a86b0abaea381edac2d5381d8db6fe5c8863f34cd6e"
AFTER = "4edbd7738e6406cef1d27793f86c3b01f9262768ad4f103d009bbe675e561e52"
OLD = b"let pulseList = DGLabPulseService.instance.pulseList;"
NEW = b"let pulseList = [...DGLabPulseService.instance.pulseList];"

parser = ArgumentParser(description="Verify or apply the waveform import overlay to a matching Hub 1.5.0 build")
parser.add_argument("hub_directory", type=Path)
parser.add_argument("--apply", action="store_true", help="Back up and update only the matching Hub program files")
args = parser.parse_args()
hub = args.hub_directory.resolve()
entry = hub / "server" / "index.js"
original = entry.read_bytes()
digest = sha256(original).hexdigest()
if digest not in {BEFORE, AFTER}:
    raise SystemExit("Hub build does not match the supported SHA-256. No files were changed.")
for rel in ("public/assets/dg-pulse-helper-CU48u3U2.js", "public/lib/zxing_full.wasm"):
    if not (hub / rel).is_file():
        raise SystemExit("Missing original Hub decoder assets. No files were changed.")
if not args.apply:
    print("Compatible Hub build; no files were changed.")
    raise SystemExit(0)
if digest == BEFORE:
    if original.count(OLD) != 1:
        raise SystemExit("Unexpected Hub code.")
    changed = original.replace(OLD, NEW, 1)
    if sha256(changed).hexdigest() != AFTER:
        raise SystemExit("Unexpected patched SHA-256.")
    backup = entry.with_name("index.js.lesta-backup")
    if backup.exists() and sha256(backup.read_bytes()).hexdigest() != BEFORE:
        raise SystemExit("Existing Hub backup is different. No files were changed.")
    if not backup.exists():
        with backup.open("xb") as file:
            file.write(original)
    temp = entry.with_name("index.js.lesta-new")
    temp.write_bytes(changed)
    temp.replace(entry)
payload = Path(__file__).resolve().parents[1] / "hub-overlay"
for rel in ("public/pulse-import-worker.js", "public/assets/pulse-file-import.js"):
    destination = hub / rel
    source = payload / rel
    if destination.exists():
        if destination.read_bytes() == source.read_bytes():
            continue
        backup = destination.with_suffix(destination.suffix + ".lesta-backup")
        if not backup.exists():
            shutil.copyfile(destination, backup)
    temp = destination.with_suffix(destination.suffix + ".lesta-new")
    shutil.copyfile(source, temp)
    temp.replace(destination)
print("Waveform import overlay installed. Restart Hub before using it.")
