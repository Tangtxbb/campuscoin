# -*- coding: utf-8 -*-
"""
区块链模块：UTXO 集合、工作量证明、难度动态调整、减半与总量上限、整链校验、持久化。

共识校验 validate_chain() 是 P2P 网络的基石：任何节点收到别人的链，
都用同一套规则独立验证，只有"有效且工作量更大"的链才会被采纳。
"""

import json
import os

from ecdsa import BadSignatureError, SECP256k1, VerifyingKey

from . import config
from .block import Block
from .merkle import merkle_root
from .transaction import Transaction
from .wallet import pubkey_to_address


# ================= 纯函数（经济模型 + 难度规则） =================

def block_subsidy(height: int) -> int:
    """第 height 个区块的补贴（不含手续费），每 HALVING_INTERVAL 减半。"""
    halvings = height // config.HALVING_INTERVAL
    subsidy = config.INITIAL_REWARD
    for _ in range(halvings):
        subsidy //= 2
        if subsidy == 0:
            break
    return subsidy


def cumulative_subsidy(up_to_height: int) -> int:
    """1 到 up_to_height 区块的补贴总和（新发行总量）。"""
    return sum(block_subsidy(h) for h in range(1, up_to_height + 1))


def expected_difficulty(chain, prev: Block) -> int:
    """计算 prev 之后下一个区块应有的难度（动态调整）。"""
    if prev.index == 0:
        return config.INITIAL_DIFFICULTY
    if prev.index % config.DIFFICULTY_ADJUST_INTERVAL != 0:
        return prev.difficulty
    # 统计最近 INTERVAL 个真实区块（不含创世块，创世块时间戳为 0 会干扰计算）
    first = chain[prev.index - config.DIFFICULTY_ADJUST_INTERVAL + 1]
    actual = (prev.timestamp - first.timestamp) / 1000.0 / config.DIFFICULTY_ADJUST_INTERVAL
    target = config.BLOCK_TIME_TARGET
    new = prev.difficulty
    if actual < target / 2:
        new += 1                 # 出块太快 -> 难度上升
    elif actual > target * 2:
        new -= 1                 # 出块太慢 -> 难度下降
    # 注意：难度按"前导 0 个数"计，每 +1 等于 16 倍难度跃升，粒度较粗，
    # 教学链设上限防止过度反应导致无法出块（真实比特币用 256 位目标值实现精细调整）。
    return min(config.MAX_DIFFICULTY, max(1, new))


def verify_tx_against(tx: Transaction, utxo: dict):
    """针对给定的 UTXO 集合校验一笔普通交易。返回 (是否有效, 说明, 输入总额)。"""
    if tx.is_coinbase():
        return False, "coinbase 不能作为普通交易", 0
    if not tx.inputs or not tx.outputs:
        return False, "交易缺少输入或输出", 0
    if tx.tx_id != tx.compute_id():
        return False, "交易 ID 不匹配", 0
    total_in = 0
    seen = set()
    for inp in tx.inputs:
        key = (inp.prev_tx_id, inp.prev_index)
        if key in seen:
            return False, "同一输出被重复引用（双花）", 0
        seen.add(key)
        ref = utxo.get(key)
        if ref is None:
            return False, "引用的输出不存在或已被花费", 0
        if not inp.public_key or not inp.signature:
            return False, "输入缺少签名", 0
        if pubkey_to_address(inp.public_key) != ref.address:
            return False, "公钥与输出地址不匹配", 0
        try:
            vk = VerifyingKey.from_string(bytes.fromhex(inp.public_key), curve=SECP256k1)
        except Exception:
            return False, "公钥非法", 0
        try:
            if not vk.verify(bytes.fromhex(inp.signature), tx.signing_hash().encode("utf-8")):
                return False, "签名验证失败", 0
        except BadSignatureError:
            return False, "签名验证失败", 0
        total_in += ref.amount
    total_out = tx.output_total()
    if total_out > total_in:
        return False, "输出金额大于输入", 0
    if total_in - total_out < config.MIN_FEE:
        return False, "手续费不足", 0
    return True, "有效", total_in


def validate_chain(chain):
    """独立校验整条链。返回 (是否有效, 说明, 累计工作量)。"""
    if not chain:
        return False, "空链", 0
    utxo = {}
    total_work = 0
    minted = 0
    for i in range(1, len(chain)):
        cur, prev = chain[i], chain[i - 1]
        if cur.index != i:
            return False, f"区块 {i} 序号错误", 0
        if cur.previous_hash != prev.hash:
            return False, f"区块 {i} 前一哈希不匹配", 0
        if cur.hash != cur.compute_hash():
            return False, f"区块 {i} 哈希校验失败", 0
        if not cur.hash.startswith("0" * cur.difficulty):
            return False, f"区块 {i} 不满足难度 {cur.difficulty}", 0
        if cur.merkle_root != merkle_root([t.tx_id for t in cur.transactions]):
            return False, f"区块 {i} Merkle 根不匹配", 0
        if cur.difficulty != expected_difficulty(chain, prev):
            return False, f"区块 {i} 难度不符", 0
        if not cur.transactions or not cur.transactions[0].is_coinbase():
            return False, f"区块 {i} 缺少 coinbase 交易", 0
        fees = 0
        for tx in cur.transactions[1:]:
            if tx.is_coinbase():
                return False, f"区块 {i} 存在多个 coinbase", 0
            ok, msg, total_in = verify_tx_against(tx, utxo)
            if not ok:
                return False, f"区块 {i}: {msg}", 0
            fees += total_in - tx.output_total()
            for inp in tx.inputs:
                utxo.pop((inp.prev_tx_id, inp.prev_index), None)
        subsidy = block_subsidy(i)
        if minted + subsidy > config.TOTAL_SUPPLY:
            subsidy = max(0, config.TOTAL_SUPPLY - minted)
        minted += subsidy
        expected_reward = subsidy + fees
        if cur.transactions[0].outputs[0].amount != expected_reward:
            return False, f"区块 {i} coinbase 金额不符", 0
        for tx in cur.transactions:
            for idx, out in enumerate(tx.outputs):
                utxo[(tx.tx_id, idx)] = out
        total_work += 1 << cur.difficulty
    return True, "整条链有效", total_work


# ================= 区块链类 =================

class Blockchain:
    def __init__(self):
        self.chain = [self._create_genesis_block()]
        self.mempool = []
        self._utxo = None
        self._utxo_dirty = True

    def _create_genesis_block(self) -> Block:
        tx = Transaction.coinbase(config.SYSTEM_ADDRESS, 0, 0)
        return Block(0, [tx], "0" * 64, timestamp=0,
                     difficulty=config.INITIAL_DIFFICULTY)

    @property
    def latest_block(self) -> Block:
        return self.chain[-1]

    @property
    def height(self) -> int:
        return len(self.chain) - 1

    # ---------- UTXO ----------
    def build_utxo_set(self) -> dict:
        utxo = {}
        for block in self.chain:
            for tx in block.transactions:
                if not tx.is_coinbase():
                    for inp in tx.inputs:
                        utxo.pop((inp.prev_tx_id, inp.prev_index), None)
                for idx, out in enumerate(tx.outputs):
                    utxo[(tx.tx_id, idx)] = out
        return utxo

    @property
    def utxo_set(self) -> dict:
        if self._utxo_dirty or self._utxo is None:
            self._utxo = self.build_utxo_set()
            self._utxo_dirty = False
        return self._utxo

    def _invalidate_utxo(self):
        self._utxo_dirty = True

    def get_utxos(self, address: str):
        return [(k, v) for k, v in self.utxo_set.items() if v.address == address]

    def get_balance(self, address: str) -> int:
        return sum(v.amount for _, v in self.get_utxos(address))

    # ---------- 交易 ----------
    def verify_transaction(self, tx: Transaction):
        return verify_tx_against(tx, self.utxo_set)

    def add_transaction(self, tx: Transaction):
        ok, msg, _ = verify_tx_against(tx, self.utxo_set)
        if not ok:
            return False, msg
        if any(t.tx_id == tx.tx_id for t in self.mempool):
            return False, "交易已存在于内存池"
        self.mempool.append(tx)
        return True, msg

    # ---------- 挖矿 ----------
    def next_difficulty(self) -> int:
        return expected_difficulty(self.chain, self.latest_block)

    def mine(self, miner_address: str) -> Block:
        """打包交易 + 区块补贴与手续费，执行 PoW，接入链尾。"""
        height = len(self.chain)
        selected = []
        for tx in list(self.mempool):
            if len(selected) >= config.MAX_TX_PER_BLOCK:
                break
            ok, _, _ = verify_tx_against(tx, self.utxo_set)
            if ok:
                selected.append(tx)

        fees = 0
        for tx in selected:
            in_sum = sum(self.utxo_set[(i.prev_tx_id, i.prev_index)].amount
                         for i in tx.inputs)
            fees += in_sum - tx.output_total()

        subsidy = block_subsidy(height)
        minted = cumulative_subsidy(height - 1)
        if minted + subsidy > config.TOTAL_SUPPLY:
            subsidy = max(0, config.TOTAL_SUPPLY - minted)
        reward = subsidy + fees

        coinbase = Transaction.coinbase(miner_address, reward, height)
        block = Block(height, [coinbase] + selected, self.latest_block.hash,
                      difficulty=self.next_difficulty())
        block.mine()

        self.chain.append(block)
        ids = {t.tx_id for t in selected}
        self.mempool = [t for t in self.mempool if t.tx_id not in ids]
        self._invalidate_utxo()
        return block

    # ---------- 校验 / 共识 ----------
    def is_chain_valid(self):
        return validate_chain(self.chain)

    def chain_work(self) -> int:
        _, _, work = validate_chain(self.chain)
        return work

    def replace_chain(self, new_chain):
        """用一条已验证的更重链替换当前链（P2P 共识用）。"""
        self.chain = new_chain
        self._invalidate_utxo()
        packed = {t.tx_id for b in new_chain for t in b.transactions}
        self.mempool = [t for t in self.mempool if t.tx_id not in packed]

    # ---------- 持久化 ----------
    def to_dict(self) -> dict:
        return {"chain": [b.to_dict() for b in self.chain]}

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False)

    def load(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.chain = [Block.from_dict(d) for d in data["chain"]]
        self._invalidate_utxo()
