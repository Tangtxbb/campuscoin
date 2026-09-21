# -*- coding: utf-8 -*-
"""
矿工客户端：连接一个链节点，持续请求挖矿。

用法：
    python scripts/miner.py --node http://127.0.0.1:8000            # 挖本机节点
    python scripts/miner.py --node http://192.168.1.100:8000 --once # 挖远程节点

说明：每个节点都持有自己的链副本。本脚本连接某个节点挖矿，该节点挖出后
会自动把新区块广播给它的所有邻居，全网同步。
"""

import argparse
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vcoin import config  # noqa: E402
from vcoin.wallet import Wallet  # noqa: E402


def load_or_create_wallet(path):
    if os.path.exists(path):
        return Wallet.load(path)
    wallet = Wallet()
    wallet.save(path)
    print(f"[钱包] 已生成新矿工钱包 -> {path}")
    return wallet


def main():
    parser = argparse.ArgumentParser(description="矿工客户端：连接节点持续挖矿")
    parser.add_argument("--node", required=True, help="节点地址")
    parser.add_argument("--wallet", default="miner_wallet.json")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    wallet = load_or_create_wallet(args.wallet)
    node = args.node.rstrip("/")
    print(f"[矿工] 地址：{wallet.address}")
    print(f"[矿工] 连接节点：{node}")
    print("[矿工] 开始挖矿…（Ctrl+C 停止）")

    try:
        while True:
            try:
                resp = requests.post(f"{node}/api/mine",
                                     json={"miner": wallet.address}, timeout=120)
                d = resp.json()
                if d.get("ok"):
                    b = d["block"]
                    reward = b["transactions"][0]["outputs"][0]["amount"]
                    print(f"[+] 挖出区块 #{b['index']}  难度 {b['difficulty']}  "
                          f"奖励 {config.fmt(reward)} {config.COIN_SYMBOL}")
                else:
                    print(f"[-] {d.get('message')}")
            except requests.exceptions.RequestException as e:
                print(f"[!] 连接失败：{e}")
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[矿工] 已停止。")


if __name__ == "__main__":
    main()
