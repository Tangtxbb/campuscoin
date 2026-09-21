# -*- coding: utf-8 -*-
"""
命令行工具：钱包（含助记词）、查余额/UTXO、转账（UTXO 选币 + 找零 + 手续费）、
挖矿、查链、查交易池、校验链、SPV 证明、邻居管理。

用法：
    python scripts/cli.py new-wallet [--file wallet.json]
    python scripts/cli.py new-hd-wallet [--file mnemonic.json]
    python scripts/cli.py balance <地址> [--node http://127.0.0.1:8000]
    python scripts/cli.py send --from wallet.json --to <地址> --amount 10 [--fee 0.001] [--node ...]
    python scripts/cli.py mine --miner <地址> [--node ...]
    python scripts/cli.py chain | mempool | validate [--node ...]
    python scripts/cli.py merkle-proof <tx_id> [--node ...]
    python scripts/cli.py peers | add-peer --peer http://... [--node ...]
"""

import argparse
import json
import os
import sys
from decimal import Decimal

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vcoin import config  # noqa: E402
from vcoin.transaction import Transaction, TxIn, TxOut  # noqa: E402
from vcoin.wallet import HDWallet, Wallet  # noqa: E402

DEFAULT_NODE = "http://127.0.0.1:8000"


def parse_coin(s) -> int:
    """把'10.5'这样的币数量转成最小单位整数。"""
    return int(Decimal(str(s)) * config.COIN)


def load_wallet(path) -> Wallet:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "private_key" in data:
        return Wallet.from_private_key_hex(data["private_key"])
    if "mnemonic" in data:
        return HDWallet.from_mnemonic(data["mnemonic"]).derive()
    raise ValueError("无法识别的钱包文件")


def cmd_new_wallet(args):
    w = Wallet()
    path = args.file or "wallet.json"
    w.save(path)
    print("已生成新钱包：")
    print(f"  地址：{w.address}")
    print(f"  私钥文件：{path}（请妥善保管，勿泄露！）")


def cmd_new_hd(args):
    hd = HDWallet.generate()
    print("助记词（请抄写到纸上妥善保存，可恢复所有地址）：")
    print(f"  {hd.mnemonic}")
    print("前 5 个派生地址：")
    for i in range(5):
        print(f"  m/44'/0'/0'/0/{i} -> {hd.address_at(i)}")
    if args.file:
        with open(args.file, "w", encoding="utf-8") as f:
            json.dump({"mnemonic": hd.mnemonic}, f, ensure_ascii=False, indent=2)
        print(f"助记词已保存到 {args.file}")


def cmd_balance(args):
    d = requests.get(f"{args.node}/api/address/{args.address}", timeout=10).json()
    print(f"地址：{args.address}")
    print(f"余额：{config.fmt(d['balance'])} {config.COIN_SYMBOL}")
    print(f"UTXO 数：{len(d['utxos'])}")


def cmd_send(args):
    wallet = load_wallet(args.src)
    amount = parse_coin(args.amount)
    fee = parse_coin(args.fee)
    utxos = requests.get(f"{args.node}/api/address/{wallet.address}", timeout=10).json()["utxos"]

    selected, total = [], 0
    for u in utxos:
        selected.append(u)
        total += u["amount"]
        if total >= amount + fee:
            break
    if total < amount + fee:
        print(f"余额不足：需要 {config.fmt(amount + fee)}，可用 {config.fmt(total)}")
        return

    inputs = [TxIn(u["tx_id"], u["index"]) for u in selected]
    outputs = [TxOut(amount, args.to)]
    change = total - amount - fee
    if change > 0:
        outputs.append(TxOut(change, wallet.address))

    tx = Transaction(inputs, outputs)
    for i in range(len(inputs)):
        tx.sign_input(i, wallet)

    r = requests.post(f"{args.node}/api/transaction", json=tx.to_dict(), timeout=10)
    d = r.json()
    print(json.dumps(d, ensure_ascii=False, indent=2))
    if d.get("ok"):
        print(f"  金额 {config.fmt(amount)}，手续费 {config.fmt(fee)}，找零 {config.fmt(change)}")


def cmd_mine(args):
    r = requests.post(f"{args.node}/api/mine", json={"miner": args.miner}, timeout=120)
    d = r.json()
    if d.get("ok"):
        b = d["block"]
        cb = b["transactions"][0]["outputs"][0]["amount"]
        print(f"挖出区块 #{b['index']}  难度 {b['difficulty']}  奖励 {config.fmt(cb)}")
    else:
        print(json.dumps(d, ensure_ascii=False, indent=2))


def cmd_chain(args):
    d = requests.get(f"{args.node}/api/chain", timeout=10).json()
    print(f"链高度：{d['height']}")
    for b in d["chain"]:
        print(f"  区块 #{b['index']}  难度 {b['difficulty']}  交易数 {len(b['transactions'])}  "
              f"哈希 {b['hash'][:16]}…")


def cmd_mempool(args):
    d = requests.get(f"{args.node}/api/mempool", timeout=10).json()
    print(f"待打包交易 {len(d['pending'])} 笔")
    for tx in d["pending"]:
        print(f"  {tx['tx_id'][:16]}…  {len(tx['inputs'])} 入 / {len(tx['outputs'])} 出")


def cmd_validate(args):
    d = requests.get(f"{args.node}/api/validate", timeout=10).json()
    print(f"校验结果：{d['message']}（累计工作量 {d['total_work']}）")


def cmd_merkle_proof(args):
    d = requests.get(f"{args.node}/api/merkle-proof/{args.tx_id}", timeout=10).json()
    if "tx_id" not in d:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return
    print(f"交易 {args.tx_id[:16]}…  在区块 #{d['block']}")
    print(f"Merkle 根：{d['merkle_root']}")
    print(f"证明路径 {len(d['proof'])} 层，SPV 验证：{'通过' if d['verified'] else '失败'}")


def cmd_peers(args):
    d = requests.get(f"{args.node}/api/peers", timeout=10).json()
    print("邻居节点：", d["peers"] or "无")


def cmd_add_peer(args):
    r = requests.post(f"{args.node}/api/peer", json={"peer": args.peer}, timeout=10)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="vcoin 命令行工具")
    parser.add_argument("--node", default=DEFAULT_NODE, help="节点地址")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new-wallet", help="生成新钱包")
    p.add_argument("--file")

    p = sub.add_parser("new-hd-wallet", help="生成助记词钱包")
    p.add_argument("--file")

    p = sub.add_parser("balance", help="查询余额")
    p.add_argument("address")

    p = sub.add_parser("send", help="发起转账")
    p.add_argument("--from", dest="src", required=True, help="发送方钱包文件")
    p.add_argument("--to", required=True, help="接收方地址")
    p.add_argument("--amount", required=True, help="转账金额（币）")
    p.add_argument("--fee", default="0", help="手续费（币）")

    p = sub.add_parser("mine", help="挖矿一次")
    p.add_argument("--miner", required=True, help="矿工地址")

    sub.add_parser("chain", help="查看链概览")
    sub.add_parser("mempool", help="查看交易池")
    sub.add_parser("validate", help="校验链")

    p = sub.add_parser("merkle-proof", help="查询交易的 SPV 证明")
    p.add_argument("tx_id")

    sub.add_parser("peers", help="查看邻居")
    p = sub.add_parser("add-peer", help="添加邻居")
    p.add_argument("--peer", required=True)

    args = parser.parse_args()
    handlers = {
        "new-wallet": cmd_new_wallet, "new-hd-wallet": cmd_new_hd,
        "balance": cmd_balance, "send": cmd_send, "mine": cmd_mine,
        "chain": cmd_chain, "mempool": cmd_mempool, "validate": cmd_validate,
        "merkle-proof": cmd_merkle_proof, "peers": cmd_peers, "add-peer": cmd_add_peer,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
