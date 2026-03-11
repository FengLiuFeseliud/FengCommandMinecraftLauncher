import json
import platform
from logging import Logger
import os
from fcml_api import FabricApi, FabricLoaderFiles, McApi, MinecrafFiles, VersionsType
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

        self.http = HttpUtils(log, retries=self.config.retries, limit=self.config.limit)
        self.mc = McApi(self.http, log)
        self.fabric = FabricApi(self.http, log)
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


    async def download_version(self, version: str):
        await self.mc.download(version)

    async def login(self):
        pass

    def _set_fabric_launch_arguments(self, fabric_json_path: str, jvm_items_str: str, jvm_str: str, versions_jar_path: str, game_arguments, lib_paths: list[str], main_class: str) -> str:
        fabric_json: FabricLoaderFiles = None
        with open(fabric_json_path, "r") as f:
            fabric_json = json.loads(f.read())
    
        for lib in fabric_json["libraries"]:
            path_dict = maven_to_path(lib["name"], ".minecraft/assets/libraries/")
            lib_paths.append(os.path.abspath(os.path.join(path_dict["path"], path_dict["lib_name"])))

        return f"java {jvm_items_str} {jvm_str};{os.path.abspath(versions_jar_path)}; {fabric_json['mainClass']} {fabric_json["arguments"]["jvm"][0]} {game_arguments}"

    def _get_launch_arguments(self, versions_files: MinecrafFiles, versions_path: str, versions_name: str, versions_jar_path: str, username: str = "test") -> str:
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
            path = os.path.abspath(os.path.join(".minecraft/assets/libraries", lib["downloads"]["artifact"]["path"]))
            if "natives" in os.path.basename(path):
                continue
            
            lib_paths.append(path)

        fabric_json_path = os.path.join(versions_path, f"{versions_files['id']}_fabric.json")
        if os.path.exists(fabric_json_path):
            launch_arguments = Template(self._set_fabric_launch_arguments(fabric_json_path, jvm_items_str, jvm_str, os.path.abspath(versions_jar_path), game_arguments, lib_paths, versions_files["mainClass"]))
        else:
            launch_arguments = Template(f"java {jvm_items_str} {jvm_str};{os.path.abspath(versions_jar_path)} {versions_files["mainClass"]} {game_arguments}")

        launch_arguments = launch_arguments.substitute(
            auth_player_name=username,
            version_name=versions_files["id"],
            game_directory=os.path.abspath(".minecraft"),
            assets_root=os.path.abspath(".minecraft/assets"),
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

    async def launch(self, versions_name: str):
        versions_path = os.path.join(".minecraft/versions", versions_name)
        versions_json_path = os.path.join(versions_path, f"{versions_name}.json")
        versions_jar_path = os.path.join(versions_path, f"{versions_name}.jar")
        asset_index_path = os.path.join(".minecraft/assets/indexes", f"{versions_name}.json")
        
        if not os.path.exists(versions_json_path) or not os.path.exists(versions_jar_path) or not os.path.exists(asset_index_path):
            self.log.error(f"版本 {versions_name} 相关文件不存在...")
            return
        
        versions_files: MinecrafFiles = None
        with open(versions_json_path, "r", encoding="utf-8") as f:
            versions_files = json.loads(f.read())

        if not versions_files:
            self.log.error(f"版本 {versions_name} 相关文件不存在...")
            return
        
        print(self._get_launch_arguments(versions_files, versions_path, versions_name, versions_jar_path))
        subprocess.run(self._get_launch_arguments(versions_files, versions_path, versions_name, versions_jar_path).split(" "))
        
    async def stop(self):
        self.config.save_config()
        await self.http.close()
        
        
        

        

        

        


