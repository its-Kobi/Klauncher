from __future__ import annotations
import json, urllib.request, urllib.parse
from typing import List, Dict, Optional

API = "https://api.modrinth.com/v2"

# project_type maps to Modrinth categories: mod, resourcepack, shader, datapack
def search_mods(query: str = "", categories: str="fabric", limit: int=20, mc_version: Optional[str]=None, project_type: str="mod") -> List[Dict]:
    q = (query or "").strip()
    # empty query => top modpacks/mods sorted by downloads, relevance on empty returns none on Modrinth
    index = "relevance" if q else "downloads"
    params = {"limit": str(limit), "index": index}
    if q:
        params["query"] = q
    facets = []
    facets.append(f'["project_type:{project_type}"]')
    if categories and project_type in ("mod","shader"):
        facets.append(f'["categories:{categories}"]')
    if mc_version:
        facets.append(f'["versions:{mc_version}"]')
    if facets:
        params["facets"] = "[" + ",".join(facets) + "]"
    url = API + "/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent":"KLauncher/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    return data.get("hits", [])

def _version_matches(filter_ver: str, candidate: str) -> bool:
    # allow "1.20" to match "1.20.1", and exact
    if filter_ver == candidate:
        return True
    if candidate.startswith(filter_ver + "."):
        return True
    if filter_ver.startswith(candidate + "."):
        return True
    return False

def get_project_versions(project_id: str, loaders: List[str]=None, game_versions: List[str]=None) -> List[Dict]:
    url = f"{API}/project/{project_id}/version"
    req = urllib.request.Request(url, headers={"User-Agent":"KLauncher/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        vers = json.loads(resp.read().decode())
    if loaders:
        vers = [v for v in vers if any(l in [x.lower() for x in v.get("loaders",[])] for l in [x.lower() for x in loaders])]
    if game_versions:
        vers = [v for v in vers if any(any(_version_matches(g, gv) for gv in v.get("game_versions",[])) for g in game_versions)]
    return vers

def pick_best_version(vers: List[Dict], mc: Optional[str], loader: Optional[str]) -> Optional[Dict]:
    if not vers:
        return None
    # sort by date_published desc (Modrinth already sorted newest first)
    # prefer exact mc match, then short match
    def score(v):
        gvs=v.get("game_versions",[])
        has_exact= any(gv==mc for gv in gvs) if mc else False
        has_short= any(_version_matches(mc, gv) for gv in gvs) if mc else False
        return (has_exact, has_short)
    vers_sorted=sorted(vers, key=lambda v: score(v), reverse=True)
    return vers_sorted[0]

def download_version_file(version: Dict, dest_dir, on_progress=None):
    import pathlib
    files = version.get("files", [])
    if not files:
        raise Exception("No files")
    # pick primary file (Modrinth marks primary:true)
    primary=[f for f in files if f.get("primary")]
    f = primary[0] if primary else files[0]
    url = f["url"]
    filename = f["filename"]
    dest = pathlib.Path(dest_dir) / filename
    req = urllib.request.Request(url, headers={"User-Agent":"KLauncher/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, 'wb') as out:
        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            out.write(chunk)
    return dest

def check_compat(project, instance) -> tuple[bool, str]:
    # defensive: project may be string if stored incorrectly
    if isinstance(project, str):
        try:
            import json as _j
            project = _j.loads(project)
        except:
            return False, f"Invalid project data: {project[:80]}"
    if not isinstance(project, dict):
        return False, f"Invalid project type: {type(project).__name__}"
    cats = project.get("categories", [])
    mc_vers = project.get("versions", [])
    loader = instance.loader
    ptype = project.get("project_type","mod")
    if ptype=="mod" and loader=="vanilla":
        return False, "Vanilla instances cannot run mods. Install Fabric/Forge/Quilt first."
    if ptype=="shader" and loader=="vanilla":
        return False, "Shader packs require a shader-compatible setup (Iris/OptiFine or Fabric/Forge with Iris). Vanilla without a loader may not support shaders."
    if loader in ("fabric","quilt","forge") and ptype in ("mod","shader"):
        low_cats = [c.lower() for c in cats]
        if loader not in low_cats and not any(loader in c for c in low_cats):
            return False, f"Incompatible loader: mod supports {cats}, instance is {loader}"
    try:
        from launcher.version_metadata import _parse_minecraft_version
        parsed = _parse_minecraft_version(instance.version_id)
        if parsed:
            base = f"{parsed[0]}.{parsed[1]}.{parsed[2]}" if parsed[2] else f"{parsed[0]}.{parsed[1]}"
            base_short = f"{parsed[0]}.{parsed[1]}"
            # lenient match: base or short matches any mc_vers via prefix
            def _matches(v):
                return any(_version_matches(base, mv) or _version_matches(base_short, mv) for mv in mc_vers)
            if mc_vers and not _matches(base):
                return True, f"Warning: not marked compatible with {base} (supports {mc_vers[:3]}...)"
    except:
        pass
    return True, ""
