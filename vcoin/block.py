# -*- coding: utf-8 -*-
"""
区块模块：区块头 + 区块体（与比特币结构一致）。

区块头（参与哈希与 PoW）：
  index / previous_hash / timestamp / difficulty / merkle_root / nonce
区块体：
  transactions（交易列表）

工作量证明：不断试 nonce，直到区块头哈希以 difficulty 个 0 开头。
"""

import hashlib
import json
import time

from .merkle import merkle_root
from .transaction import Transaction


class Block:
    def __init__(self, index, transactions, previous_hash, timestamp=None,
                 difficulty=None, nonce=0, block_hash=None):
        self.index = index
        self.transactions = transactions           # list[Transaction]
        self.previous_hash = previous_hash
        self.timestamp = int(timestamp) if timestamp is not None else int(time.time() * 1000)
        self.difficulty = difficulty               # 本区块难度
        self.nonce = nonce
        self.merkle_root = merkle_root([t.tx_id for t in transactions])
        self.hash = block_hash or self.compute_hash()

    def header_dict(self) -> dict:
        """区块头（不含交易体），是哈希与 PoW 的对象。"""
        return {
            "index": self.index,
            "previous_hash": self.previous_hash,
            "timestamp": self.timestamp,
            "difficulty": self.difficulty,
            "merkle_root": self.merkle_root,
            "nonce": self.nonce,
        }

    def compute_hash(self) -> str:
        payload = json.dumps(self.header_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def mine(self) -> str:
        """工作量证明：暴力枚举 nonce，直到哈希满足难度。"""
        target = "0" * self.difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.compute_hash()
        return self.hash

    def to_dict(self):
        return {
            "index": self.index,
            "transactions": [t.to_dict() for t in self.transactions],
            "previous_hash": self.previous_hash,
            "timestamp": self.timestamp,
            "difficulty": self.difficulty,
            "merkle_root": self.merkle_root,
            "nonce": self.nonce,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            index=d["index"],
            transactions=[Transaction.from_dict(t) for t in d["transactions"]],
            previous_hash=d["previous_hash"],
            timestamp=d["timestamp"],
            difficulty=d["difficulty"],
            nonce=d["nonce"],
            block_hash=d["hash"],
        )
