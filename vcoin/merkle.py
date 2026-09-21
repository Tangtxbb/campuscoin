# -*- coding: utf-8 -*-
"""
Merkle 树：把一批交易哈希"折叠"成单个根哈希（Merkle root），放进区块头。

价值（这就是正规币比玩具链多的关键之一）：
1. 区块头只存一个 32 字节的根，就能"代表"整块所有交易。
2. 支持 SPV 轻验证：手机钱包不用下载整条链，只要一条 Merkle 证明
   （约 log₂(n) 个哈希）就能确认某笔交易确实在某区块里。
"""

import hashlib


def sha256d(data: str) -> str:
    """双重 SHA256（比特币的标准做法），输入输出都是十六进制字符串。"""
    return hashlib.sha256(hashlib.sha256(data.encode("utf-8")).digest()).hexdigest()


def _pair(left: str, right: str) -> str:
    return sha256d(left + right)


def merkle_root(tx_ids: list) -> str:
    """由交易 ID 列表计算 Merkle 根。"""
    if not tx_ids:
        return "0" * 64
    level = list(tx_ids)
    while len(level) > 1:
        if len(level) % 2 == 1:          # 奇数个则复制最后一个
            level.append(level[-1])
        level = [_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def merkle_proof(tx_ids: list, index: int):
    """生成第 index 个交易的 Merkle 证明。

    返回 [(兄弟哈希, 是否在左侧), ...]，从下往上。
    """
    if not tx_ids or index < 0 or index >= len(tx_ids):
        return None
    level = list(tx_ids)
    proof = []
    i = index
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        if i % 2 == 0:
            proof.append((level[i + 1], False))   # 兄弟在右侧
        else:
            proof.append((level[i - 1], True))    # 兄弟在左侧
        level = [_pair(level[j], level[j + 1]) for j in range(0, len(level), 2)]
        i //= 2
    return proof


def verify_proof(root: str, tx_id: str, proof: list) -> bool:
    """用 Merkle 证明验证 tx_id 是否属于根为 root 的树。"""
    h = tx_id
    for sibling, is_left in proof:
        h = _pair(sibling, h) if is_left else _pair(h, sibling)
    return h == root
