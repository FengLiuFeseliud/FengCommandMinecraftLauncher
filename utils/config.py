from logging import Logger
from yaml.loader import SafeLoader
import yaml
import os


class Config:
    retries: int = 3
    limit: int = 16
    chunk_size: int = 128

    def __init__(self, log: Logger):
        self.log = log

    def get_configs(self) -> None:
        return {
            "retries": self.retries,
            "limit": self.limit,
            "chunk_size": self.chunk_size
        }

    def save_config(self) -> None:
        with open("./config.yaml", "w") as f:
            f.write(yaml.dump(self.get_configs(), default_flow_style=False))

    def _init_config(self, config: any, val: any) -> any:
        if self.yaml is not None and config in self.yaml:
            return self.yaml[config]
        
        return val

    def _yaml_to_config(self, yaml: dict):
        self.yaml = yaml

        self.retries = self._init_config("retries", 3)
        self.limit = self._init_config("limit", 16)
        self.chunk_size = self._init_config("chunk_size", 128)

    def read_config(self):
        if not os.path.exists("./config.yaml"):
            self.save_config()
            self.log.info("")
            return
        
        with open("./config.yaml", "r") as f:
            self._yaml_to_config(yaml.load(f.read(), Loader=SafeLoader))
