from abc import ABCMeta, abstractmethod
import os


MOJANG_URL = "https://launchermeta.mojang.com"
MC_URL = "https://piston-meta.mojang.com"
ASSETS_URL = "http://resources.download.minecraft.net"
LIBRARIES_URL = "https://libraries.minecraft.net"
FABRIC_URL = "https://meta.fabricmc.net"
FABRIC_LIBRARIES_URL = "https://maven.fabricmc.net"
FOREG_URL = "https://files.minecraftforge.net"
FOREG_LIBRARIES_URL = "https://maven.minecraftforge.net"


class Mirror(metaclass=ABCMeta):
    
    @abstractmethod
    def get_mirror_url(self) -> str:
        pass

    def to_mirror_path(self, path: str) -> str:
        return f"{self.get_mirror_url()}{path}"
    
    def get_mc_url(self) -> str:
        return self.get_mirror_url()
    
    def to_mc_url(self, assets_url: str) -> str:
        return assets_url.replace(MC_URL, self.get_mc_url())
    
    def get_assets_url(self) -> str:
        return f"{self.get_mirror_url()}/assets"
    
    def to_assets_url(self, assets_url: str) -> str:
        return assets_url.replace(ASSETS_URL, self.get_assets_url())
    
    def to_assets_path(self, path: str) -> str:
        return f"{self.get_assets_url()}{path}"
    
    def get_libraries_url(self) -> str:
        return f"{self.get_mirror_url()}/maven"
    
    def to_libraries_url(self, libraries_url) -> str:
        return libraries_url.replace(LIBRARIES_URL, self.get_libraries_url())
    
    def get_fabric_url(self) -> str:
        return f"{self.get_mirror_url()}/fabric-meta"
    
    def to_fabric_url(self, fabric_url: str) -> str:
        return fabric_url.replace(FABRIC_URL, self.get_fabric_url())
    
    def to_fabric_path(self, path: str) -> str:
        return f"{self.get_fabric_url()}{path}"
    
    def get_fabric_libraries_url(self) -> str:
        return self.get_libraries_url()
    
    def to_fabric_libraries_url(self, fabric_url: str) -> str:
        return fabric_url.replace(FABRIC_LIBRARIES_URL, self.get_fabric_libraries_url())
    
    def get_forge_url(self) -> str:
        return f"{self.get_mirror_url()}/forge"
    
    def to_forge_url(self, forge_url: str) -> str:
        return forge_url.replace(FOREG_URL, self.get_forge_url())
    
    def to_forge_path(self, path: str) -> str:
        return f"{self.get_forge_url()}{path}"
    
    def get_forge_libraries_url(self) -> str:
        return self.get_libraries_url()
    
    def to_forge_libraries_url(self, forge_url: str) -> str:
        return forge_url.replace(FOREG_LIBRARIES_URL, self.get_forge_libraries_url())
    
    def to_forge_libraries_path(self, path: str) -> str:
        return f"{self.get_forge_libraries_url()}{path}"


class McMirror(Mirror):

    def get_mirror_url(self):
        return MC_URL
    
    def get_mc_url(self):
        return MC_URL
    
    def get_assets_url(self):
        return ASSETS_URL
    
    def get_libraries_url(self):
        return LIBRARIES_URL
    
    def get_fabric_url(self):
        return FABRIC_URL

    def get_fabric_libraries_url(self):
        return FABRIC_LIBRARIES_URL
    
    def get_forge_url(self):
        return FOREG_URL
    
    def get_forge_libraries_url(self):
        return FOREG_LIBRARIES_URL


class BmclMirror(Mirror):

    def get_mirror_url(self):
        return "https://bmclapi2.bangbang93.com"