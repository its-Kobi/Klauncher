from __future__ import annotations
from launcher.providers.base import VersionProvider
from launcher.providers.vanilla import VanillaProvider
from launcher.providers.fabric import FabricProvider
from launcher.providers.forge import ForgeProvider
from launcher.providers.quilt import QuiltProvider
from launcher.providers.optifine import OptiFineProvider
from launcher.providers.custom import CustomProvider

_PROVIDERS = {
    "vanilla": VanillaProvider(),
    "fabric": FabricProvider(),
    "forge": ForgeProvider(),
    "quilt": QuiltProvider(),
    "optifine": OptiFineProvider(),
    "custom": CustomProvider(),
}

_order = ["vanilla","fabric","forge","quilt","optifine","custom"]

def get_registry():
    return _PROVIDERS

def get_provider(pid: str) -> VersionProvider:
    return _PROVIDERS.get(pid, _PROVIDERS["vanilla"])

def list_loader_types():
    from launcher.providers.base import LoaderType
    return [
        LoaderType("vanilla","Vanilla","Clean Minecraft"),
        LoaderType("fabric","Fabric","Lightweight mod loader"),
        LoaderType("forge","Forge","Classic mod loader"),
        LoaderType("quilt","Quilt","Fabric fork"),
        LoaderType("optifine","OptiFine","HD graphics"),
        LoaderType("custom","Custom","Local version"),
    ]
