from __future__ import annotations
from pathlib import Path
import hashlib

def health_check(instance, java_manager):
    report=[]
    # Java check
    try:
        required=instance.required_java()
        chosen=instance.settings_overrides.get("java_path") or java_manager.find_compatible(required)
        if isinstance(chosen, str):
            path=chosen
        elif chosen:
            path=chosen.path
        else:
            path=None
        ok,msg=java_manager.validate_for_launch(required, path)
        if not ok:
            report.append(("ERROR", f"Java incompatible: requires Java {required}", f"Download Java {required}"))
        else:
            report.append(("OK", f"Java {required} compatible", None))
    except Exception as e:
        report.append(("WARN", f"Java check failed: {e}", None))
    # Mods checks
    try:
        mods_dir=instance.game_dir / "mods"
        if mods_dir.exists():
            files=list(mods_dir.glob("*.jar")) + list(mods_dir.glob("*.jar.disabled"))
            names={}
            for f in files:
                names.setdefault(f.name.lower(), []).append(f)
            for n, lst in names.items():
                if len(lst)>1:
                    report.append(("WARN", f"Duplicate mod file: {n} ({len(lst)} copies)", "Remove duplicate"))
            # corrupted check: zero byte
            for f in files:
                try:
                    if f.stat().st_size==0:
                        report.append(("ERROR", f"Corrupted (0 byte) mod: {f.name}", "Remove/reinstall"))
                except: pass
            # duplicate mod id via fabric.mod.json (best effort)
            import zipfile, json
            ids={}
            for f in mods_dir.glob("*.jar"):
                try:
                    with zipfile.ZipFile(f) as z:
                        if "fabric.mod.json" in z.namelist():
                            data=json.loads(z.read("fabric.mod.json").decode())
                            mid=data.get("id")
                            if mid:
                                ids.setdefault(mid, []).append(f.name)
                except: pass
            for mid, lst in ids.items():
                if len(lst)>1:
                    report.append(("ERROR", f"Conflicting mods same ID '{mid}': {', '.join(lst)}", "Remove one"))
    except Exception as e:
        report.append(("WARN", f"Mods check failed: {e}", None))
    # missing instance json
    if not (instance.path / "instance.json").exists():
        report.append(("ERROR","Missing instance.json","Recreate instance"))
    return report

def auto_fix(instance, report, java_manager, parent=None):
    fixed=0
    for sev,msg,fix in report:
        if "Download Java" in (fix or ""):
            try:
                import re
                m=re.search(r"Java (\d+)", fix)
                if m:
                    required=int(m.group(1))
                    # trigger download synchronously? use manager async then save
                    java_manager.download_java(required)
                    fixed+=1
            except: pass
        if "Remove duplicate" in (fix or ""):
            try:
                mods_dir=instance.game_dir / "mods"
                seen=set()
                for f in sorted(mods_dir.glob("*.jar.disabled"), reverse=True):
                    # keep first enabled
                    pass
                # remove exact duplicate filenames case-insensitive keep one
                from collections import defaultdict
                d=defaultdict(list)
                for f in list(mods_dir.glob("*.jar")):
                    d[f.name.lower()].append(f)
                for lst in d.values():
                    if len(lst)>1:
                        for dup in lst[1:]:
                            dup.unlink(missing_ok=True); fixed+=1
            except: pass
        if "Remove/reinstall" in (fix or ""):
            try:
                # remove zero-byte
                for f in (instance.game_dir / "mods").glob("*.jar"):
                    if f.stat().st_size==0:
                        f.unlink(missing_ok=True); fixed+=1
            except: pass
    return fixed
