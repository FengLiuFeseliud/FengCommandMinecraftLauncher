from abc import ABCMeta, abstractmethod
import asyncio, aiofiles
from logging import Logger
from rich.progress import BarColumn, DownloadColumn, Progress, TransferSpeedColumn
import hashlib
import aiohttp
import os
from mirror import *


class HttpUtils:
    def __init__(self, log: Logger, retries: int = 3, limit: int = 12, chunk_size: int = 1024, mirror: str | None = None):
        self.retries = retries
        self.limit = limit
        self.session = None
        self.log = log
        self.chunk_size = chunk_size

        if mirror == "bmcl":
            self.mirror = BmclMirror()
        else:
            self.mirror = McMirror()
        
        self.progress = Progress(
            *Progress.get_default_columns(), 
            DownloadColumn(binary_units=True), 
            TransferSpeedColumn(), 
            transient=True
        )
        self.progress.start()

    def get_session(self):
        if self.session == None:
            conn = aiohttp.TCPConnector(limit=self.limit)
            timeout = aiohttp.ClientTimeout(sock_read=120, total=None)

            self.session = aiohttp.ClientSession(connector=conn, timeout=timeout)
        return self.session

    async def get(self, url: str, retries_count: int = 0):
        try:
            async with self.get_session().get(url) as response:
                return await response.json()
        except Exception as err:
            retries_count += 1
            if retries_count == self.retries:
                return
        
            return await self.get(url, retries_count)
        
    async def get_text(self, url: str, retries_count: int = 0):
        try:
            async with self.get_session().get(url) as response:
                return await response.text()
        except Exception as err:
            retries_count += 1
            if retries_count == self.retries:
                return
        
            return await self.get_text(url, retries_count)
    
    async def download_file(self, url: str, path: str, file_name: str, sha1: str | None, size: int, retries_count: int = 0):
        if retries_count == self.retries:
            return

        file_down_path = f"{path}/{file_name}"
        if os.path.exists(file_down_path):
            self.log.debug(f"文件 {file_name} 存在, 跳过")
            return
        
        os.makedirs(path, exist_ok=True)

        file_sha1 = None
        if sha1 != None:
            file_sha1 = hashlib.sha1()

        progress_task = self.progress.add_task(f"下载 {file_name}...", total=size, visible=False)
        try:
            async with self.get_session().get(url) as response:
                async with aiofiles.open(file_down_path, 'wb') as f:
                    self.progress.reset(progress_task, total=size, visible=True)
                    while True:
                        chunk = await response.content.read(self.chunk_size * 1024)
                        if file_sha1 != None:
                            file_sha1.update(chunk)
                        
                        if not chunk:
                            break

                        await f.write(chunk)
                        self.progress.update(progress_task, advance=len(chunk))
                
                if sha1 != None and file_sha1.hexdigest() != sha1:
                    raise ValueError(f"SHA1 校验失败: 期望 {sha1}, 实际 {file_sha1.hexdigest()}")
                
            self.progress.remove_task(progress_task)
        except Exception as err:
            retries_count += 1
            if os.path.exists(file_down_path):
                self.log.debug(f"下载失败清理残留文件 {file_down_path}")
                os.remove(file_down_path)
            
            self.log.warning(f"下载 {file_name} 失败 {type(err).__name__}: {str(err)}, 重试次数 {retries_count}/{self.retries}")

            await asyncio.sleep(1)
            self.progress.remove_task(progress_task)
            await self.download_file(url, path, file_name, sha1, size, retries_count)

    async def _download_worker(self, queue: asyncio.Queue):
        while not queue.empty():
            await queue.get_nowait()
            queue.task_done()
    
    async def download_tasks(self, task_queue: asyncio.Queue):
        [asyncio.create_task(self._download_worker(task_queue)) for _ in range(self.limit)]
        await task_queue.join()

    async def close(self):
        self.progress.stop()
        
        if not self.session is None:
            await self.session.close()
        self.session = None