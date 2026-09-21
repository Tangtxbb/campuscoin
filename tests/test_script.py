# -*- coding: utf-8 -*-
"""单元测试：智能合约脚本 VM（多签 + 时间锁）。"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vcoin import Blockchain, Transaction, TxIn, TxOut, Wallet, config  # noqa: E402
from vcoin.script import multisig_lock, run_script, timelock_lock  # noqa: E402

COIN = config.COIN


class TestScriptVM(unittest.TestCase):
    def test_multisig_2of3(self):
        k = [Wallet(), Wallet(), Wallet()]
        pubs = [w.public_key_hex() for w in k]
        lock = multisig_lock(pubs, 2)
        sighash = "ab" * 32
        ok_unlock = ["PUSH", k[0].sign(sighash), "PUSH", k[2].sign(sighash)]
        self.assertTrue(run_script(lock, ok_unlock, {"sighash": sighash}))
        one_unlock = ["PUSH", k[0].sign(sighash)]
        self.assertFalse(run_script(lock, one_unlock, {"sighash": sighash}))
        bad_unlock = ["PUSH", k[0].sign(sighash), "PUSH", k[1].sign("cd" * 32)]
        self.assertFalse(run_script(lock, bad_unlock, {"sighash": sighash}))

    def test_timelock(self):
        w = Wallet()
        now = int(time.time() * 1000)
        lock = timelock_lock(w.public_key_hex(), now + 60_000)
        sig = w.sign("ab" * 32)
        self.assertFalse(run_script(lock, ["PUSH", sig], {"sighash": "ab" * 32, "now": now}))
        self.assertTrue(run_script(lock, ["PUSH", sig], {"sighash": "ab" * 32, "now": now + 120_000}))


class TestScriptOnChain(unittest.TestCase):
    """脚本输出真正上链、再花掉的全流程。"""

    def test_multisig_spend(self):
        chain = Blockchain()
        alice = Wallet(); bob = Wallet()
        k = [Wallet(), Wallet(), Wallet()]

        chain.mine(alice.address)
        cb = chain.chain[1].transactions[0]
        lock = multisig_lock([w.public_key_hex() for w in k], 2)
        tx1 = Transaction([TxIn(cb.tx_id, 0)], [TxOut(50 * COIN, script=lock)])
        tx1.sign_input(0, alice)
        self.assertTrue(chain.add_transaction(tx1)[0])
        chain.mine(alice.address)

        tx2 = Transaction([TxIn(tx1.tx_id, 0)], [TxOut(50 * COIN, bob.address)])
        sh = tx2.signing_hash()
        tx2.inputs[0].unlock_script = ["PUSH", k[0].sign(sh), "PUSH", k[2].sign(sh)]
        ok, msg = chain.add_transaction(tx2)
        self.assertTrue(ok, msg)

        tx3 = Transaction([TxIn(tx1.tx_id, 0)], [TxOut(50 * COIN, bob.address)])
        tx3.inputs[0].unlock_script = ["PUSH", k[0].sign(tx3.signing_hash())]
        self.assertFalse(chain.add_transaction(tx3)[0])

        ok, msg, _ = chain.is_chain_valid()
        self.assertTrue(ok, msg)


if __name__ == "__main__":
    unittest.main()
