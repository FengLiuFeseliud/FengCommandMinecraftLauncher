import json
import platform
from logging import Logger
import os

import aiofiles
from fcml_api import FabricApi, FabricLoaderFiles, ForgeApi, McApi, MinecrafFiles, VersionsType
from utils.config import Config
from utils.http_utils import HttpUtils
from string import Template
from rich.prompt import Prompt
from rich.console import Console
from rich.table import Table
from rich import print
from datetime import datetime
from utils.path_util import maven_to_path
import subprocess


class MinecraftLauncher:
    def __init__(self, log: Logger):
        self.config = Config(log)
        self.config.read_config()

        self.minecraft_dir = self.config.minecraft_dir
        self.assets_dir = os.path.join(self.minecraft_dir, "assets")
        self.libraries_dir = os.path.join(self.assets_dir, "libraries")
        self.versions_dir = os.path.join(self.minecraft_dir, "versions")

        self.http = HttpUtils(log, retries=self.config.retries, limit=self.config.limit, chunk_size=self.config.chunk_size, mirror = self.config.mirror)
        self.mc = McApi(self.http, log)
        self.fabric = FabricApi(self.http, log)
        self.forge = ForgeApi(self.http, log)
        self.log = log

    async def get_versions(self):
        version_list = await self.mc.get_version_list()
        page_version_lists = [version_list[i:i+20] for i in range(0, len(version_list), 20)]

        console = Console()
        for page_version_list in page_version_lists:
            table = Table(title="已查询版本", expand=True)

            table.add_column("发布时间", no_wrap=True)
            table.add_column("版本号", no_wrap=True)
            table.add_column("版本类型", no_wrap=True)
            table.add_column("版本文件")

            for version in page_version_list:
                table.add_row(
                    datetime.fromisoformat(version["releaseTime"]).strftime("%Y-%m-%d %H:%M:%S"),
                    version["id"],
                    version["type"],
                    version["url"]
                )

            console.print(table)
            Prompt.ask("回车显示下一页...")

    def to_versions_path(self, versions_name: str) -> str:
        return os.path.join(self.versions_dir, versions_name)
    
    def get_versions_minecraft_id(self, versions_name: str) -> str | None:
        versions_json_path = os.path.join(self.to_versions_path(versions_name), f"{versions_name}.json")
        if not os.path.exists(versions_json_path):
            return
        
        with open(versions_json_path, 'r') as f:
            version: MinecrafFiles = json.loads(f.read())
            return version["id"] if "id" in version else None

    async def download_minecraft(self, version: str, versions_name: str | None = None):
        await self.mc.download(version, self.minecraft_dir, self.to_versions_path(versions_name if not versions_name is None else version), versions_name)

    async def download_fabric(self, loader_version: str, versions_name: str):
        version_path = self.to_versions_path(versions_name)
        if not os.path.exists(version_path):
            self.log.error(f"目标版本 {versions_name} Minecraft 不存在... 请先下载")
            return
        
        minecraft_version = self.get_versions_minecraft_id(versions_name)
        if minecraft_version is None:
            self.log.error(f"无法获取目标版本 {versions_name} Minecraft 版本")
            return

        await self.fabric.download(loader_version, minecraft_version, version_path, self.minecraft_dir)
    

    async def login(self):
        pass

    def _set_fabric_launch_arguments(self, fabric_json_path: str, jvm_items_str: str, jvm_str: str, game_arguments, lib_paths: list[str]) -> str:
        fabric_json: FabricLoaderFiles = None
        with open(fabric_json_path, "r") as f:
            fabric_json = json.loads(f.read())
    
        for lib in fabric_json["libraries"]:
            path_dict = maven_to_path(lib["name"], self.libraries_dir)
            lib_paths.append(os.path.abspath(os.path.join(path_dict["path"], path_dict["lib_name"])))
    
        return f"java {jvm_items_str} {jvm_str} {fabric_json["arguments"]["jvm"][0].replace(" ","")} {fabric_json['mainClass']} {game_arguments}"

    def _get_launch_arguments(
            self, 
            versions_files: MinecrafFiles, 
            versions_path: str, 
            versions_name: str, 
            versions_jar_path: str, 
            username: str = "test"
        ) -> str:
        os_name = platform.system().lower()
        machine = platform.machine().lower().replace("_64", "")
        jvm = versions_files["arguments"]["jvm"]

        jvm_str = " ".join([item for item in jvm if type(item) is str])
        jvm_items = [item for item in jvm if type(item) is dict]
        jvm_items_str = None

        for jvm_item in jvm_items:
            if "arch" in jvm_item["rules"][0]["os"]["name"]:
                if jvm_item["rules"]["os"]["archname"] in machine:
                    jvm_items_str = jvm_item["value"]
                break

            if os_name == jvm_item["rules"][0]["os"]["name"]:
                jvm_items_str = jvm_item["value"]
                break
        
        if not jvm_items_str:
            jvm_items_str = jvm_items[-1]["value"]

        game_arguments = " ".join([arguments for arguments in versions_files["arguments"]["game"] if type(arguments) is str])

        lib_paths = []
        for lib in versions_files["libraries"]:
            if "downloads" not in lib or "artifact" not in lib["downloads"]:
                continue

            path = os.path.abspath(os.path.join(self.libraries_dir, lib["downloads"]["artifact"]["path"]))
            if "natives" in os.path.basename(path):
                continue
            
            lib_paths.append(path)

        fabric_json_path = os.path.join(versions_path, "fabric.json")
        if os.path.exists(fabric_json_path):
            launch_arguments = Template(self._set_fabric_launch_arguments(fabric_json_path, jvm_items_str, jvm_str, game_arguments, lib_paths))
        else:
            launch_arguments = Template(f'java {jvm_items_str} {jvm_str} {versions_files["mainClass"]} {game_arguments}')

        lib_paths.append(os.path.abspath(versions_jar_path))
        launch_arguments = launch_arguments.substitute(
            auth_player_name=username,
            version_name=versions_files["id"],
            game_directory=os.path.abspath(self.minecraft_dir),
            assets_root=os.path.abspath(os.path.join(self.minecraft_dir, "assets")),
            assets_index_name=versions_files["id"],
            auth_uuid="00000000-0000-0000-0000-000000000000",
            auth_access_token=0,
            clientid=0,
            auth_xuid=0,
            version_type="FCML",
            user_type=0,
            natives_directory=os.path.abspath(os.path.join(versions_path, f"{versions_name}_natives")),
            launcher_name="FCML",
            launcher_version=versions_files["id"],
            classpath=";".join(lib_paths)
        )

        return launch_arguments

    def reset_versions_name(self):
        pass

    async def launch(self, versions_name: str):
        versions_path = self.to_versions_path(versions_name)
        versions_json_path = os.path.join(versions_path, f"{versions_name}.json")
        versions_jar_path = os.path.join(versions_path, f"{versions_name}.jar")
        
        if not os.path.exists(versions_json_path) or not os.path.exists(versions_jar_path):
            self.log.error(f"版本 {versions_name} 相关文件不存在...")
            return
        
        versions_files: MinecrafFiles = None
        with open(versions_json_path, "r", encoding="utf-8") as f:
            versions_files = json.loads(f.read())

        asset_index_path = os.path.join(self.assets_dir, f"indexes/{versions_files["id"]}.json")
        if not versions_files or not os.path.exists(asset_index_path):
            self.log.error(f"版本 {versions_name} 相关文件不存在...")
            return
        
        subprocess.run(self._get_launch_arguments(versions_files, versions_path, versions_name, versions_jar_path).split(" "))
        
    async def stop(self):
        self.config.save_config()
        await self.http.close()
        
        
        

        

        

        


