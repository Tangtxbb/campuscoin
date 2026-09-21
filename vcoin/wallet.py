# -*- coding: utf-8 -*-
"""
钱包模块：
1. Wallet  —— 单个密钥对（随机生成或从私钥恢复），地址 = SHA256(公钥) 前 40 位。
2. HDWallet —— 分层确定性钱包：助记词(BIP39) -> 种子 -> 主密钥 -> 派生多个地址。

真实世界里，正规钱包都用「助记词」而不是直接保存私钥：
你只要记下 12/24 个英文单词，就能在任意设备恢复出所有地址和币。
"""

import hashlib
import hmac
import json
import os

from ecdsa import SECP256k1, SigningKey
from mnemonic import Mnemonic

ADDRESS_LEN = 40


def pubkey_to_address(pubkey_hex: str) -> str:
    """由公钥（十六进制）推导出地址。"""
    return hashlib.sha256(bytes.fromhex(pubkey_hex)).hexdigest()[:ADDRESS_LEN]


class Wallet:
    """一个密钥对 + 一个地址。"""

    def __init__(self, signing_key=None):
        self.signing_key = signing_key or SigningKey.generate(curve=SECP256k1)
        self.public_key = self.signing_key.get_verifying_key()
        self.address = pubkey_to_address(self.public_key.to_string().hex())

    def private_key_hex(self) -> str:
        return self.signing_key.to_string().hex()

    def public_key_hex(self) -> str:
        return self.public_key.to_string().hex()

    @classmethod
    def from_private_key_hex(cls, hex_str: str) -> "Wallet":
        return cls(SigningKey.from_string(bytes.fromhex(hex_str), curve=SECP256k1))

    @classmethod
    def from_private_key_bytes(cls, b: bytes) -> "Wallet":
        return cls(SigningKey.from_string(b, curve=SECP256k1))

    def sign(self, message: str) -> str:
        return self.signing_key.sign(message.encode("utf-8")).hex()

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"address": self.address, "private_key": self.private_key_hex()},
                      f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "Wallet":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        wallet = cls.from_private_key_hex(data["private_key"])
        assert wallet.address == data["address"], "钱包文件损坏"
        return wallet


# ---------------- HD 钱包（BIP39 + BIP32 简化） ----------------

def _master_key(seed: bytes):
    """BIP32 主密钥：HMAC-SHA512(key='Bitcoin seed', data=seed)。"""
    i = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
    return i[:32], i[32:]          # (私钥, 链码)


def _ckd_priv(priv: bytes, chain: bytes, index: int):
    """BIP32 硬化子密钥派生（index 已含 0x80000000 硬化标志）。"""
    data = b"\x00" + priv + index.to_bytes(4, "big")
    i = hmac.new(chain, data, hashlib.sha512).digest()
    return i[:32], i[32:]


class HDWallet:
    """助记词钱包：一个助记词可派生无穷多个地址。"""

    def __init__(self, mnemonic_words: str, passphrase: str = ""):
        self.mnemonic = mnemonic_words
        self.seed = Mnemonic("english").to_seed(mnemonic_words, passphrase)
        self.master_priv, self.master_chain = _master_key(self.seed)

    @classmethod
    def generate(cls, strength: int = 128) -> "HDWallet":
        """随机生成助记词（128 位熵 = 12 个单词，256 位 = 24 个单词）。"""
        return cls(Mnemonic("english").generate(strength))

    @classmethod
    def from_mnemonic(cls, words: str, passphrase: str = "") -> "HDWallet":
        m = Mnemonic("english")
        if not m.check(words):
            raise ValueError("助记词无效（校验和失败），请检查单词是否写错")
        return cls(words, passphrase)

    def derive(self, path: str = "m/44'/0'/0'/0/0") -> Wallet:
        """按路径派生私钥。简化实现：所有层级都按硬化派生处理
        （硬化派生只用私钥，无需公钥运算，足够钱包安全使用）。"""
        priv, chain = self.master_priv, self.master_chain
        for comp in path.split("/")[1:]:
            idx = int(comp.rstrip("'")) | 0x80000000
            priv, chain = _ckd_priv(priv, chain, idx)
        return Wallet.from_private_key_bytes(priv)

    def address_at(self, index: int) -> str:
        """第 index 个账户地址（m/44'/0'/0'/0/{index}）。"""
        return self.derive(f"m/44'/0'/0'/0/{index}").address

    def addresses(self, n: int) -> list:
        return [self.address_at(i) for i in range(n)]
