from abc import ABC, abstractmethod

class BaseModule(ABC):
    def __init__(self, config):
        self.config = config

    @abstractmethod
    def run(self):
        pass
