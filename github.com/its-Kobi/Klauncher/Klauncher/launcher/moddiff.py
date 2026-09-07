from __future__ import annotations
from pathlib import Path

def diff_mods(old_list, new_list):
    """old_list/new_list: list of (name, version)"""
    old={n:v for n,v in old_list}
    new={n:v for n,v in new_list}
    added=[(n,new[n]) for n in new if n not in old]
    removed=[(n,old[n]) for n in old if n not in new]
    bumped=[(n,old[n],new[n]) for n in old if n in new and old[n]!=new[n]]
    return added, removed, bumped
