from abc import ABCMeta, abstractmethod
from logging import Logger
import json, asyncio, os, platform
from threading import Thread
import glob
import zipfile
from rich.progress import Progress, TaskID, track
from typing import Annotated, Collection, List, Literal, TypedDict, Coroutine
from mirror import BmclMirror
from utils.http_utils import HttpUtils
from utils.path_util import maven_to_path
from lxml import etree


LWJGL_PATH = ".minecraft/assets/libraries/org/lwjgl"

MinecraftVersionsType = Annotated[Literal["release", "snapshot"], "游戏版本类型"]
VersionsType = MinecraftVersionsType | Literal["all"]


class LatestInfo(TypedDict):
    release: str
    snapshot: str


class VersionsItem(TypedDict):
    id: str
    type: MinecraftVersionsType
    url: str
    time: str
    releaseTime: str


class MinecraftVersions(TypedDict):
    latest: LatestInfo
    versions: List[VersionsItem]


class AssetIndex(TypedDict):
    id: str
    sha1: str
    size: int
    totalSize: int
    url: str


class MinecrafDownloadItem(TypedDict):
    sha1: str
    size: int
    url: str


class MinecrafDownloads(TypedDict):
    client: MinecrafDownloadItem
    client_mappings: MinecrafDownloadItem
    server: MinecrafDownloadItem
    server_mappings: MinecrafDownloadItem


class JavaVersion(TypedDict):
    component: str
    majorVersion: int


class LibrariesDownloads(TypedDict):
    path: str
    sha1: str
    size: int
    url: str


class LibrariesRules(TypedDict):
    action: str
    os: dict["name": str]


class LibrariesItem(TypedDict):
    downloads: dict["artifact": LibrariesDownloads]
    name: str
    rules: list[LibrariesRules]


class LoggingFile(TypedDict):
    id: str
    sha1: str
    size: int
    url: str


class LoggingItemClient(TypedDict):
    argument: str
    file: LoggingFile


class LoggingItem(TypedDict):
    client: LoggingItemClient
    type: str


class MinecrafFiles(TypedDict):
    arguments: dict
    assetIndex: AssetIndex
    assets: str
    complianceLevel: int
    downloads: MinecrafDownloads
    id: str
    javaVersion: JavaVersion
    libraries: List[LibrariesItem]
    mainClass: str
    minimumLauncherVersion: int
    releaseTime: str
    time: str
    type: str
    logging: LoggingItem
    mainClass: str


class AssetItem(TypedDict):
    hash: str
    size: int


class DownloadApi(metaclass=ABCMeta):

    def __init__(self, http: HttpUtils, log: Logger):
        self.http = http
        self.log = log
        self.progress = None

    @abstractmethod
    async def get_version(self, versions: str) -> any:
        pass
    
    @abstractmethod
    async def get_files(self, versions: any) -> any:
        pass
    
    @abstractmethod
    async def get_files(self, versions: any) -> any:
        pass

    @abstractmethod
    async def download(self, versions: any) -> any:
        pass

    def _get_progress(self) -> Progress:
        if self.progress == None:
            self.progress = Progress()

        return self.progress
    

class LoaderApi(metaclass=ABCMeta):

    @abstractmethod
    async def get_loader_versions(self, mc_version: str, latest: bool = False) -> any | List[any]:
        pass


class McApi(DownloadApi):
    
    def __init__(self, http: HttpUtils, log: Logger):
        super().__init__(http, log)
        self.versions = None

    def __get_latest_versions(self, versions: MinecraftVersions, versions_type: VersionsType) -> List[VersionsItem]:
        latest = versions["latest"]

        if versions_type == "all":
            return [version for version in versions["versions"] if version["id"] == latest["release"] or version["id"] == latest["snapshot"]]
         
        return [version for version in versions["versions"] if version["id"] == latest[versions_type]]

    async def get_version_list(self, versions_type: VersionsType = "all", latest: bool = False) -> List[VersionsItem]:
        versions: MinecraftVersions = await self.http.get(self.http.mirror.to_mirror_path("/mc/game/version_manifest.json"))

        if latest:
            return self.__get_latest_versions(versions, versions_type)
        
        if versions_type == "all":
            return versions["versions"]

        return [version for version in versions["versions"] if version["id"] == versions_type]
    
    async def get_version(self, versions: str) -> VersionsItem | None:
        for item in await self.get_version_list():
            if item["id"] == versions:
                return item
        
        return None
    
    async def get_files(self, versions: VersionsItem) -> MinecrafFiles:
        return await self.http.get(versions["url"])

    async def get_assets(self, asset_index: AssetIndex) -> dict["objects": dict["path": AssetItem]]:
        return await self.http.get(asset_index["url"])

    def _get_download_client_task(self, versions_files: MinecrafFiles, version_name: str, download_dir_path: str):
        client = versions_files["downloads"]["client"]

        return self.http.download_file(
            self.http.mirror.to_mc_url(client["url"]), 
            download_dir_path,
            f"{version_name}.jar",
            client["sha1"],
            client["size"]
        )
    
    def _get_download_logging_task(self, versions_files: MinecrafFiles, minecraft_dir_path: str):
        logging = versions_files["logging"]["client"]["file"]

        return self.http.download_file(
            self.http.mirror.to_mc_url(logging["url"]), 
            os.path.join(minecraft_dir_path, "log_config"),
            logging["id"],
            logging["sha1"],
            logging["size"]
        )
    
    async def __download_assets(self, asset: AssetItem, assets_path: str, progressTask: TaskID) -> None:
        file_hash = asset["hash"]
        hash_path = file_hash[0:2]

        await self.http.download_file(
            self.http.mirror.to_assets_path(f"/{hash_path}/{file_hash}"), 
            os.path.join(assets_path, f"objects/{hash_path}"),
            file_hash,
            file_hash,
            asset["size"]
        )
        self._get_progress().update(progressTask, advance=1)
        
    async def _put_download_assets_task(self, asset_index: dict["path": AssetItem], queue: asyncio.Queue, assets_path: str) -> None:
        progress_task = self._get_progress().add_task("下载资源文件...", total=len(asset_index["objects"].keys()))
        for _, asset  in asset_index["objects"].items():
            await queue.put(self.__download_assets(asset, assets_path, progress_task))
    
    async def __download_libraries(self, artifact: LibrariesDownloads, libraries_path: str, progressTask: TaskID) -> None:
        await self.http.download_file(
            self.http.mirror.to_libraries_url(artifact["url"]),
            os.path.join(libraries_path, os.path.dirname(artifact["path"])),
            os.path.basename(artifact["path"]),
            artifact["sha1"],
            artifact["size"]
        )
        self._get_progress().update(progressTask, advance=1)

    def _get_use_libraries_list(self, librariesList: List[LibrariesItem]) -> List[LibrariesItem]:
        use_libraries_list = []
        os_name = platform.system().lower()

        for libraries in librariesList:
            if "rules" in libraries and libraries["rules"][-1]["os"]["name"] != os_name:
                continue
            
            use_libraries_list.append(libraries)

        return use_libraries_list

    async def _put_download_libraries_task(self, librariesList: List[LibrariesItem], queue: asyncio.Queue, libraries_path: str) -> None:
        librariesList = self._get_use_libraries_list(librariesList)
        progress_task = self._get_progress().add_task("下载库文件...", total=len(librariesList))
        os_name = platform.system().lower()

        for libraries in librariesList:
            if "rules" in libraries and libraries["rules"][-1]["os"]["name"] != os_name:
                continue
            
            # 旧版本下载 natives
            if "classifiers" in libraries["downloads"]:
                await queue.put(self.__download_libraries(libraries["downloads"]["classifiers"][f"natives-{os_name}"], libraries_path, progress_task))
                continue

            await queue.put(self.__download_libraries(libraries["downloads"]["artifact"], libraries_path, progress_task))
    
    def _extract_natives_task(self, file_path: str, out_path: str) -> Thread:
        with zipfile.ZipFile(file_path, "r") as jar:
            target_path = [name for name in jar.namelist() if ".dll" in name and ".dll." not in name][0]
            if not target_path:
                return
            
            os.makedirs(out_path, exist_ok=True)
            out_file = os.path.join(out_path, os.path.basename(target_path))
            with open(out_file, "wb") as f:
                f.write(jar.read(target_path))
            
            self.log.info(f"解压 natives 库 dll {target_path} 完成")

    def _extract_natives(self, versions_files: MinecrafFiles, version_name: str, version_path: str, libraries_dir_path: str):
        if not os.path.exists(os.path.join(libraries_dir_path, "org/lwjgl")):
            return
        
        os_name = platform.system().lower()
        machine = platform.machine().lower()
        if machine not in ["x86_64", "arm64"]:
            machine = None

        lwjgl_lib = []
        for lib in versions_files["libraries"]:
            if "org/lwjgl/" not in lib["downloads"]['artifact']["path"]:
                continue
            
            lwjgl_lib.append(os.path.join(libraries_dir_path, f"{lib["downloads"]['artifact']["path"]}"))

                
        flie_list = None
        if machine:
            flie_list = [lwjgl for lwjgl in lwjgl_lib if machine in lwjgl and os_name in lwjgl] 
        else:
            flie_list = [lwjgl for lwjgl in lwjgl_lib if "x86" not in lwjgl and "arm64" not in lwjgl and "natives" in lwjgl and os_name in lwjgl]

        threads = []
        for file_path in flie_list:
            thread = Thread(target=self._extract_natives_task, args=(file_path, os.path.join(version_path, f"{version_name}_natives")))
            thread.daemon = True
            thread.name = "extract_natives_task"
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

    def _save_versions_files_task(self, versions_files: MinecrafFiles, versions_files_json_path: str):
        with open(versions_files_json_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(versions_files, indent=4, ensure_ascii=False))
        self.log.info(f"版本文件保存至 {versions_files_json_path}")

    def _save_versions_files(self, versions_files: MinecrafFiles, versions_files_json_path: str):
        thread = Thread(target=self._save_versions_files_task, args=(versions_files, versions_files_json_path))
        thread.daemon = True
        thread.name = "save_versions_files_task"
        thread.start()

    async def download(self, version: str, minecraf_dir: str, version_path: str, version_name: str | None) -> None:
        versions_item = await self.get_version(version)
        versions_id = versions_item["id"]

        if not version_name:
            version_name = versions_id

        self.log.info(f"获取版本 {versions_id} 完成")

        if not os.path.exists(version_path):
            os.makedirs(version_path)
        
        versions_files_json_path = os.path.join(version_path, f"{version_name}.json")
        versions_files = None
        if not os.path.isfile(versions_files_json_path):
            versions_files = await self.get_files(versions_item)
            self.log.info(f"获取版本文件完成")
            self._save_versions_files(versions_files, versions_files_json_path)

        else:
            with open(versions_files_json_path, "r") as f:
                versions_files = json.loads(f.read())
            self.log.info(f"读取版本文件完成")

        asset_index = await self.get_assets(versions_files["assetIndex"])
        self.log.info(f"获取资源索引文件完成")

        asset_index_dir_path = os.path.join(minecraf_dir, f"assets/indexes")
        if not os.path.isdir(asset_index_dir_path):
            os.makedirs(asset_index_dir_path)
        
        assets_indexes_json_path = os.path.join(asset_index_dir_path, f"{versions_id}.json")
        with open(assets_indexes_json_path, "w", encoding="utf-8") as f:
           f.write(json.dumps(asset_index))
        self.log.info(f"资源索引文件保存至 {assets_indexes_json_path}")

        self._get_progress().start()

        task_queue = asyncio.Queue()
        libraries_dir_path = os.path.join(minecraf_dir, f"assets/libraries")
        await task_queue.put(self._get_download_client_task(versions_files, version_name, version_path))
        await task_queue.put(self._get_download_logging_task(versions_files, minecraf_dir))
        await self._put_download_assets_task(asset_index, task_queue, os.path.join(minecraf_dir, f"assets"))
        await self._put_download_libraries_task(versions_files["libraries"], task_queue, libraries_dir_path)
        self.log.info(f"下载任务创建完成, 共 {task_queue.qsize()} 项下载任务")
        await self.http.download_tasks(task_queue)

        self._extract_natives(versions_files, version_name, version_path, libraries_dir_path)
        self.progress.stop()
        self.progress = None

        self.log.info(f"下载版本 {versions_id} 成功")


class FabricLoaderLibrary(TypedDict):
    name: str
    url: str
    sha1: str
    sha256: str
    sha512: str
    size: int


class FabricLoaderVersions(TypedDict):
    loader: dict["separator": str, "build": int, "version": str, "stable": bool, "maven": str]
    intermediary: dict["maven": str, "version": int, "stable": bool]
    launcherMeta: dict["version": int, "min_java_version": int, 
                       "libraries": dict["client": List[FabricLoaderLibrary], "common": List[FabricLoaderLibrary]], "server": List[FabricLoaderLibrary],
                       "mainClass": dict["client": str, "server": str]]
    

class FabricLoaderFiles(TypedDict):
    version: str
    inheritsFrom: str
    releaseTime: str
    time: str
    type: str
    mainClass: str
    arguments: dict["game": List[str], "jvm": List[str]]
    libraries: List[FabricLoaderLibrary] 


class FabricApi(DownloadApi, LoaderApi):

    def __init__(self, http: HttpUtils, log: Logger):
        super().__init__(http, log)

    async def get_loader_versions(self, mc_version: str, latest: bool = False) -> FabricLoaderVersions | List[FabricLoaderVersions]:
        loader_versions_list = await self.http.get(self.http.mirror.to_fabric_path(f"/v2/versions/loader/{mc_version}"))
        return loader_versions_list[0] if latest else loader_versions_list
    
    async def get_version(self, loader_version: str, mc_version: str) -> FabricLoaderVersions | None:
        for loader in await self.get_loader_versions(mc_version):
            if loader["loader"]["version"] != loader_version:
                continue

            return loader
        return None
    
    async def get_files(self, loader_version: FabricLoaderVersions) -> FabricLoaderFiles:
        version = loader_version["loader"]["version"]
        mc_version = loader_version["intermediary"]["version"]
        return await self.http.get(self.http.mirror.to_fabric_path(f"/v2/versions/loader/{mc_version}/{version}/profile/json"))
    
    async def __download_libraries(self, lib_url: str, path: str, lib_name: str, sha1: str | None, size: int, progressTask: TaskID) -> None:
        await self.http.download_file(lib_url, path, lib_name, sha1, size)
        self._get_progress().update(progressTask, advance=1)

    
    async def _put_download_libraries_task(self, loader_version: FabricLoaderVersions, queue: asyncio.Queue, minecraft_dir: str):
        libs = loader_version["libraries"]

        libraries_dir_path = os.path.join(minecraft_dir, f"assets/libraries")
        progress_task = self._get_progress().add_task("下载库文件...", total=len(libs))
        for lib in libs:

            path_dict = maven_to_path(lib["name"], libraries_dir_path)
            lib_url = f"{lib["url"]}{path_dict["lib_sub_path"]}/{path_dict["name"]}/{path_dict["var"]}/{path_dict["lib_name"]}"

            if "size" not in lib:
                lib["size"] = 0

            if "sha1" not in lib:
                await queue.put(self.__download_libraries(
                    self.http.mirror.to_fabric_libraries_url(lib_url), path_dict["path"], path_dict["lib_name"], None, lib["size"], progress_task))
                continue
            
            await queue.put(self.__download_libraries(
                self.http.mirror.to_fabric_libraries_url(lib_url), path_dict["path"], path_dict["lib_name"], lib["sha1"], lib["size"], progress_task))

    async def download_from_file(self, fabric_loader_files: FabricLoaderFiles, version_path: str, minecraft_dir: str) -> None:
        loader_versions_id = fabric_loader_files["id"]
        self.log.info(f"获取 Fabric 版本 {loader_versions_id} 完成")

        fabric_loader_files_json_path = os.path.join(version_path, "fabric.json")
        with open(fabric_loader_files_json_path, "w") as f:
            f.write(json.dumps(fabric_loader_files))

        self._get_progress().start()

        task_queue = asyncio.Queue()
        await self._put_download_libraries_task(fabric_loader_files, task_queue, minecraft_dir)
        self.log.info(f"下载任务创建完成, 共 {task_queue.qsize()} 项下载任务")
        await self.http.download_tasks(task_queue)

        self.progress.stop()
        self.progress = None

        self.log.info(f"下载 Fabric 版本 {loader_versions_id} 成功")
    
    async def download(self, loader_version: str, mc_version: str, version_path: str, minecraft_dir: str) -> None:
        loader_version = await self.get_version(loader_version, mc_version)
        if loader_version is None:
            self.log.error(f"Minecraft 版本 {mc_version} 不存在可用 {loader_version} fabric")
            return

        await self.download_from_file(await self.get_files(loader_version), version_path, minecraft_dir)


class ForgeLoaderVersions(TypedDict):
    loader: str
    time: str
    mc_version: str
    

class ForgeApi(DownloadApi, LoaderApi):

    def __init__(self, http, log):
        super().__init__(http, log)
    
    async def get_loader_versions(self, mc_version, latest = False) -> ForgeLoaderVersions | List[ForgeLoaderVersions]:
        if type(self.http.mirror) is BmclMirror:
            data = await self.http.get(self.http.mirror.to_forge_path(f"/minecraft/{mc_version}"))
            if latest:
                data = data[-1]
                return {"loader": data["version"], "time": data["modified", "mc_version": mc_version]} 
            
            return [{"loader": item["version"], "time": item["modified"], "mc_version": mc_version} for item in data]
        
        data = await self.http.get_text(self.http.mirror.to_forge_path(f"/net/minecraftforge/forge/index_{mc_version}.html"))
        versions = etree.HTML(data).xpath("/html/body/main/div[2]/div[2]/div[2]/table/tbody/tr")

        versions_list = []
        if latest:
            versions = versions[0]
            return {
                "loader": versions.xpath(".//*[@class='download-version']/text()")[0].replace("\n", "").replace(" ", ""),
                "time": versions.xpath(".//*[@class='download-time']/@title")[0],
                "mc_version": mc_version
            }
        
        for item in ([versions[0]] if latest else versions):
            versions_list.append({
                "loader": item.xpath(".//*[@class='download-version']/text()")[0].replace("\n", "").replace(" ", ""),
                "time": item.xpath(".//*[@class='download-time']/@title")[0],
                "mc_version": mc_version
            })

        return versions_list
        

    def get_files(self, versions: ForgeLoaderVersions):
        loader_name = f"{versions["mc_version"]}-{versions['loader']}"
        return self.http.mirror.to_forge_libraries_path(f"/net/minecraftforge/forge/{loader_name}/forge-{loader_name}-installer.jar")
    
    def get_version(self, versions: List[ForgeLoaderVersions], loader_version: str) -> ForgeLoaderVersions:
        for item in versions:
            if item["loader"] == loader_version:
                return item
            
        return None

    async def download(self, loader_version: str, mc_version: str, version_name: str | None = None) -> None:
        if not version_name:
            version_name = mc_version
        
        if not os.path.exists(f".minecraft/versions/{version_name}"):
            self.log.error(f"目标版本 {version_name} Minecraft 不存在... 请先下载")
            return
        
        loader_version = self.get_version(await self.get_loader_versions(mc_version), loader_version)
        if loader_version is None:
            return
        
        self.log.info(f"获取 Forge 版本 {loader_version["loader"]} 完成")
        installer_jar_url = self.get_files(loader_version)

        await self.http.download_file(installer_jar_url)
