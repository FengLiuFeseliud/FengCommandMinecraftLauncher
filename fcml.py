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

    fcml = MinecraftLauncher(log) 
    
    try:
        if len(sys.argv) < 2:
            await fcml.download_version("1.17")
            await fcml.launch("1.17")
            return

        if sys.argv[1] == "help":
            print("Usage: python fcml.py [command]")
            print("Commands:")
            print("  help - Show this help message")
            print("  download [version] - Download a specific Minecraft version")
            print("  login - Log in to your Minecraft account")
            print("  launch - Launch Minecraft")
    except Exception as err:
        log.exception(err)
    finally:
        await fcml.stop()

if __name__ == "__main__":
    asyncio.run(main())