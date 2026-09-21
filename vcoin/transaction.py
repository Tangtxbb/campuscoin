# -*- coding: utf-8 -*-
"""
UTXO 交易模型（比特币同款思路）。

一笔交易不是"从 A 账户减 10、给 B 账户加 10"，而是：
  - 输入（inputs）：引用之前别人转给你的、还没花掉的若干笔"输出"，并逐个签名解锁。
  - 输出（outputs）：产生新的可被花费的输出，锁定给某个地址。
  - 找零：输入总额 - 转出金额 - 手续费 = 找零，一般转回给自己。

未花费的输出叫 UTXO（Unspent Transaction Output），全网维护一张 UTXO 集合。
"""

import hashlib
import json
import time

from ecdsa import BadSignatureError, SECP256k1, VerifyingKey

from . import config
from .wallet import pubkey_to_address


class TxIn:
    """交易输入：引用一笔已存在的输出，并签名/脚本"解锁"它。"""

    def __init__(self, prev_tx_id, prev_index, public_key=None, signature=None,
                 unlock_script=None):
        self.prev_tx_id = prev_tx_id       # 引用的交易 ID
        self.prev_index = int(prev_index)  # 引用的输出序号
        self.public_key = public_key       # 解锁用的公钥（普通地址支付）
        self.signature = signature         # 解锁用的签名（普通地址支付）
        self.unlock_script = unlock_script  # 可选：脚本解锁数据（智能合约）

    def to_dict(self):
        return {"prev_tx_id": self.prev_tx_id, "prev_index": self.prev_index,
                "public_key": self.public_key, "signature": self.signature,
                "unlock_script": self.unlock_script}

    @classmethod
    def from_dict(cls, d):
        return cls(d["prev_tx_id"], d["prev_index"],
                   d.get("public_key"), d.get("signature"),
                   d.get("unlock_script"))


class TxOut:
    """交易输出：一笔"锁给某地址/某脚本"的钱，将来可被花费。"""

    def __init__(self, amount, address=None, script=None):
        self.amount = int(amount)          # 最小单位（聪）
        self.address = address             # 收款地址（无脚本时用）
        self.script = script               # 可选：自定义锁定脚本（智能合约）

    def to_dict(self):
        return {"amount": self.amount, "address": self.address, "script": self.script}

    @classmethod
    def from_dict(cls, d):
        return cls(d["amount"], d.get("address"), d.get("script"))


class Transaction:
    def __init__(self, inputs, outputs, timestamp=None, data=""):
        self.inputs = inputs               # list[TxIn]
        self.outputs = outputs             # list[TxOut]
        self.timestamp = int(timestamp) if timestamp is not None else int(time.time() * 1000)
        self.data = data                   # 附加数据（coinbase 用它保证唯一性）
        self.tx_id = self.compute_id()

    def is_coinbase(self):
        return len(self.inputs) == 1 and self.inputs[0].prev_tx_id == "0" * 64

    def _core_dict(self):
        """参与 tx_id 和签名的核心内容（不含签名本身，避免循环依赖）。"""
        return {
            "inputs": [{"prev_tx_id": i.prev_tx_id, "prev_index": i.prev_index}
                       for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "timestamp": self.timestamp,
            "data": self.data,
        }

    def compute_id(self) -> str:
        payload = json.dumps(self._core_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def signing_hash(self) -> str:
        """签名对象：锁定所有输入引用 + 全部输出，防止金额/收款人被篡改。"""
        return self.compute_id()

    def sign_input(self, index: int, wallet) -> None:
        """用钱包给第 index 个输入签名。"""
        self.inputs[index].public_key = wallet.public_key_hex()
        self.inputs[index].signature = wallet.sign(self.signing_hash())

    def output_total(self) -> int:
        return sum(o.amount for o in self.outputs)

    @classmethod
    def coinbase(cls, miner_address, reward, height) -> "Transaction":
        """挖矿奖励交易：无真实输入，输出 = 区块补贴 + 手续费，给矿工。"""
        return cls([TxIn("0" * 64, -1)], [TxOut(reward, miner_address)],
                   data=f"coinbase-{height}")

    def to_dict(self):
        return {
            "tx_id": self.tx_id,
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "timestamp": self.timestamp,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d):
        return cls([TxIn.from_dict(i) for i in d["inputs"]],
                   [TxOut.from_dict(o) for o in d["outputs"]],
                   d["timestamp"], d.get("data", ""))
