# -*- coding: utf-8 -*-
"""单元测试：UTXO 交易、Merkle 树、减半、难度调整、防双花、整链校验。
运行：python -m unittest discover -s tests"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vcoin import (  # noqa: E402
    Blockchain, Transaction, TxIn, TxOut, Wallet,
    merkle_proof, merkle_root, verify_proof,
)
from vcoin import config  # noqa: E402
from vcoin.chain import block_subsidy, expected_difficulty  # noqa: E402

COIN = config.COIN


def spend_utxo(chain, wallet, utxo_key, outputs):
    """构造一笔花掉某 UTXO 的已签名交易。utxo_key=(tx_id, index)。"""
    tx = Transaction([TxIn(utxo_key[0], utxo_key[1])], outputs)
    tx.sign_input(0, wallet)
    return tx


class TestMining(unittest.TestCase):
    def setUp(self):
        self.chain = Blockchain()
        self.miner = Wallet()

    def test_genesis(self):
        self.assertEqual(len(self.chain.chain), 1)
        self.assertEqual(self.chain.chain[0].index, 0)

    def test_mining_valid_block(self):
        b = self.chain.mine(self.miner.address)
        self.assertEqual(b.index, 1)
        self.assertTrue(b.hash.startswith("0" * b.difficulty))
        self.assertEqual(b.previous_hash, self.chain.chain[0].hash)

    def test_mining_reward(self):
        self.chain.mine(self.miner.address)
        self.assertEqual(self.chain.get_balance(self.miner.address), config.INITIAL_REWARD)

    def test_subsidy_halving(self):
        self.assertEqual(block_subsidy(0), config.INITIAL_REWARD)
        self.assertEqual(block_subsidy(config.HALVING_INTERVAL),
                         config.INITIAL_REWARD // 2)
        self.assertEqual(block_subsidy(2 * config.HALVING_INTERVAL),
                         config.INITIAL_REWARD // 4)

    def test_expected_difficulty(self):
        self.assertEqual(expected_difficulty(self.chain.chain, self.chain.chain[0]),
                         config.INITIAL_DIFFICULTY)


class TestUTXO(unittest.TestCase):
    def setUp(self):
        self.chain = Blockchain()
        self.miner = Wallet()
        self.alice = Wallet()
        self.bob = Wallet()

    def test_transfer_with_change(self):
        self.chain.mine(self.alice.address)           # alice 得 50 币
        cb = self.chain.chain[1].transactions[0]      # coinbase
        key = (cb.tx_id, 0)
        outputs = [TxOut(20 * COIN, self.bob.address),
                   TxOut(29 * COIN, self.alice.address)]  # 找零 29，手续费 1
        tx = spend_utxo(self.chain, self.alice, key, outputs)
        ok, _ = self.chain.add_transaction(tx)
        self.assertTrue(ok)
        self.chain.mine(self.miner.address)
        self.assertEqual(self.chain.get_balance(self.alice.address), 29 * COIN)
        self.assertEqual(self.chain.get_balance(self.bob.address), 20 * COIN)

    def test_double_spend_rejected(self):
        self.chain.mine(self.alice.address)
        cb = self.chain.chain[1].transactions[0]
        # 两个输入引用同一个 UTXO
        tx = Transaction([TxIn(cb.tx_id, 0), TxIn(cb.tx_id, 0)],
                         [TxOut(60 * COIN, self.bob.address)])
        tx.sign_input(0, self.alice)
        tx.sign_input(1, self.alice)
        ok, msg = self.chain.add_transaction(tx)
        self.assertFalse(ok)
        self.assertIn("双花", msg)

    def test_tampered_output_rejected(self):
        self.chain.mine(self.alice.address)
        cb = self.chain.chain[1].transactions[0]
        tx = spend_utxo(self.chain, self.alice, (cb.tx_id, 0),
                        [TxOut(30 * COIN, self.bob.address)])
        tx.outputs[0].amount = 99 * COIN   # 篡改收款金额，不重新签名
        ok, _ = self.chain.add_transaction(tx)
        self.assertFalse(ok)


class TestMerkle(unittest.TestCase):
    def test_root_and_proof(self):
        ids = [f"tx{i:064d}" for i in range(5)]
        root = merkle_root(ids)
        for i in range(5):
            proof = merkle_proof(ids, i)
            self.assertTrue(verify_proof(root, ids[i], proof))
        self.assertFalse(verify_proof(root, "forged" * 8 + "0000", merkle_proof(ids, 0)))

    def test_empty_root(self):
        self.assertEqual(merkle_root([]), "0" * 64)


class TestChainValidation(unittest.TestCase):
    def setUp(self):
        self.chain = Blockchain()
        self.miner = Wallet()

    def test_valid_chain(self):
        self.chain.mine(self.miner.address)
        self.chain.mine(self.miner.address)
        ok, msg, work = self.chain.is_chain_valid()
        self.assertTrue(ok, msg)
        self.assertGreater(work, 0)

    def test_tamper_detected(self):
        self.chain.mine(self.miner.address)
        self.chain.chain[1].transactions[0].outputs[0].amount += 1
        ok, _, _ = self.chain.is_chain_valid()
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
