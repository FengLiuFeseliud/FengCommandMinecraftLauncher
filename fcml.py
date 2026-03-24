from argparse import ArgumentParser
import logging
from rich.logging import RichHandler
from minecraft_launcher import MinecraftLauncher
import asyncio
import sys


async def main():
    FORMAT = "%(message)s"
    logging.basicConfig(
        level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
    )
    log = logging.getLogger("rich")

    parser = ArgumentParser()

    subparsers = parser.add_subparsers(dest="command")
    install = subparsers.add_parser("install", help="安装资源")
    install.add_argument("-f", "--fabric", type=str, nargs='?', const="latest", help="安装指定 fabric, 为空值时下载最新可用 fabric")
    install.add_argument("-m", "--minecraft", type=str, help="安装指定 Minecraft")
    install.add_argument("-n", "--name", type=str, required=True, help="指定版本名称 (必须)")

    launch = subparsers.add_parser("launch", help="启动版本")
    launch.add_argument("-n", "--name", type=str, help="指定启动版本名称")

    args = parser.parse_args()
    
    fcml = MinecraftLauncher(log)
    try:
        if args.command == "install":
             if not args.minecraft is None:
                await fcml.download_minecraft(args.minecraft, args.name)
             
             if not args.fabric is None:
                loader_version = args.fabric
                if loader_version== "latest":
                    mc_version = fcml.get_versions_minecraft_id(args.name)
                    if mc_version is None:
                        log.error(f"无法获取目标版本 {args.name} Minecraft 版本")
                        return
                    loader_version = (await fcml.fabric.get_loader_versions(mc_version, True))["loader"]["version"]

                await fcml.download_fabric(loader_version, args.name)

        if args.command == "launch":
            if args.name is None:
                return
            
            await fcml.launch(args.name)

    except Exception as err:
        log.exception(err)
    finally:
        await fcml.stop()

if __name__ == "__main__":
    asyncio.run(main())