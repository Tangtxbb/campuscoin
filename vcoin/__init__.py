# -*- coding: utf-8 -*-
"""vcoin：一个用于学习区块链原理的迷你公链（UTXO + PoW + P2P + 智能合约脚本）。"""

from .block import Block
from .chain import Blockchain
from .merkle import merkle_proof, merkle_root, verify_proof
from .script import multisig_lock, run_script, timelock_lock
from .transaction import Transaction, TxIn, TxOut
from .wallet import HDWallet, Wallet

__all__ = [
    "Block", "Blockchain", "Transaction", "TxIn", "TxOut",
    "Wallet", "HDWallet", "merkle_root", "merkle_proof", "verify_proof",
    "multisig_lock", "timelock_lock", "run_script",
]
