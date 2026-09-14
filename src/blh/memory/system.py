"""Memory 门面:组合存储/召回/提取,暴露给 Harness 的集成接口。"""

from .extract import MemoryExtractor
from .recall import MemoryRecall
from .store import MemoryStore


class Memory:
    def __init__(self, store: MemoryStore, provider):
        self.store = store
        self.provider = provider
        self.recall = MemoryRecall(store, provider)
        self.extractor = MemoryExtractor(store, provider)

    def system_section(self, messages) -> str:
        relevant = self.recall.load_memories(messages)
        return self.recall.build_system(relevant)

    def extract(self, messages) -> int:
        return self.extractor.extract_memories(messages)

    def consolidate(self) -> int:
        return self.extractor.consolidate_memories()
