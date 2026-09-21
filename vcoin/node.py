# -*- coding: utf-8 -*-
"""
P2P 链节点：每个节点都独立持有一份链，通过 HTTP 互相同步、广播区块与交易。

启动：
    python -m vcoin.node                          # 单节点
    python -m vcoin.node --port 8000 --peer http://127.0.0.1:8001   # 连接邻居
    python -m vcoin.node --port 8000 --mine --miner <地址>          # 边挖边同步

共识规则（Nakamoto 最重链）：
    节点收到别人的链后独立验证，只有当它「有效」且「累计工作量更大」时才采纳；
    若双方工作量相同，用区块头哈希较小者打破平局，保证全网收敛到同一条链。

HTTP API（用户用）：
    GET  /                  区块浏览器页面
    GET  /api/info          节点信息
    GET  /api/chain         整条链
    GET  /api/block/<index> 单个区块
    GET  /api/tx/<tx_id>    按 ID 查交易
    GET  /api/address/<addr> 余额 + UTXO
    GET  /api/mempool       交易池
    GET  /api/validate      校验链
    GET  /api/merkle-proof/<tx_id>  SPV 轻验证证明
    POST /api/transaction   提交交易（会广播）
    POST /api/mine          挖矿（会广播）
P2P（节点间用）：
    GET  /api/peers         邻居列表
    POST /api/peer          添加邻居
    POST /api/block         接收广播的区块
    POST /api/tx            接收广播的交易
"""

import os
import threading
import time

import requests as http

from flask import Flask, jsonify, request

from . import config
from .block import Block
from .chain import Blockchain, validate_chain
from .merkle import merkle_proof, verify_proof
from .transaction import Transaction

EXPLORER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "explorer.html")


class Node:
    def __init__(self, data_dir, port, peers=(), mine=False, miner_address=None):
        self.data_dir = data_dir
        self.port = port
        self.peers = set(peers)
        self.mine_flag = mine
        self.miner_address = miner_address
        self.chain_file = os.path.join(data_dir, "chain.json")

        self.chain = Blockchain()
        if os.path.exists(self.chain_file):
            try:
                self.chain.load(self.chain_file)
                print(f"[节点] 已加载历史链，高度 {self.chain.height}")
            except Exception as e:
                print(f"[节点] 加载失败，使用全新链：{e}")

        self._lock = threading.RLock()
        self.app = self._build_app()

    # ---------------- 持久化 ----------------
    def _persist(self):
        with self._lock:
            self.chain.save(self.chain_file)

    # ---------------- 广播 ----------------
    def _broadcast_block(self, block):
        data = block.to_dict()
        for peer in list(self.peers):
            try:
                http.post(f"{peer}/api/block", json=data, timeout=5)
            except Exception:
                pass

    def _broadcast_tx(self, tx):
        data = tx.to_dict()
        for peer in list(self.peers):
            try:
                http.post(f"{peer}/api/tx", json=data, timeout=5)
            except Exception:
                pass

    # ---------------- 同步（最重链共识） ----------------
    def _chain_key(self, chain):
        """用于比较两条链谁更优：(累计工作量, 末块哈希)。"""
        ok, _, work = validate_chain(chain)
        return (work, chain[-1].hash) if ok else (-1, chain[-1].hash)

    def sync(self):
        best_chain = None
        best_key = self._chain_key(self.chain.chain)
        for peer in list(self.peers):
            try:
                data = http.get(f"{peer}/api/chain", timeout=10).json()
                candidate = [Block.from_dict(b) for b in data["chain"]]
                key = self._chain_key(candidate)
                if key[0] >= 0 and key > best_key:
                    best_chain, best_key = candidate, key
            except Exception:
                continue
        if best_chain is not None:
            with self._lock:
                self.chain.replace_chain(best_chain)
                self._persist()
            print(f"[同步] 采纳更优链，高度 {len(best_chain) - 1}")

    def _sync_loop(self):
        while True:
            try:
                self.sync()
            except Exception as e:
                print("[同步] 出错：", e)
            time.sleep(config.SYNC_INTERVAL)

    def _mine_loop(self):
        while True:
            try:
                with self._lock:
                    block = self.chain.mine(self.miner_address)
                    self._persist()
                print(f"[挖矿] 新区块 #{block.index} 难度 {block.difficulty}")
                self._broadcast_block(block)
            except Exception as e:
                print("[挖矿] 出错：", e)
            time.sleep(1)

    # ---------------- Flask 应用 ----------------
    def _build_app(self):
        app = Flask(__name__)

        @app.after_request
        def cors(resp):
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
            return resp

        # ---- 区块浏览器 ----
        @app.route("/")
        def explorer():
            if os.path.exists(EXPLORER_FILE):
                with open(EXPLORER_FILE, "r", encoding="utf-8") as f:
                    return f.read()
            return jsonify({"message": "explorer.html 缺失"})

        # ---- 查询类 ----
        @app.route("/api/info")
        def info():
            ok, _, work = validate_chain(self.chain.chain)
            return jsonify({
                "coin": config.COIN_NAME, "symbol": config.COIN_SYMBOL,
                "height": self.chain.height,
                "difficulty": self.chain.latest_block.difficulty,
                "subsidy": config.fmt(self._subsidy()),
                "peers": list(self.peers),
                "valid": ok,
                "total_work": work,
            })

        @app.route("/api/chain")
        def get_chain():
            return jsonify({"height": self.chain.height,
                            "chain": [b.to_dict() for b in self.chain.chain]})

        @app.route("/api/block/<int:index>")
        def get_block(index):
            if 0 <= index < len(self.chain.chain):
                return jsonify(self.chain.chain[index].to_dict())
            return jsonify({"ok": False, "message": "区块不存在"}), 404

        @app.route("/api/tx/<tx_id>")
        def get_tx(tx_id):
            for b in self.chain.chain:
                for tx in b.transactions:
                    if tx.tx_id == tx_id:
                        return jsonify({"block": b.index, "tx": tx.to_dict()})
            for tx in self.chain.mempool:
                if tx.tx_id == tx_id:
                    return jsonify({"block": None, "tx": tx.to_dict()})
            return jsonify({"ok": False, "message": "交易不存在"}), 404

        @app.route("/api/address/<address>")
        def get_address(address):
            utxos = [{"tx_id": k[0], "index": k[1], "amount": v.amount}
                     for k, v in self.chain.get_utxos(address)]
            return jsonify({
                "address": address,
                "balance": self.chain.get_balance(address),
                "utxos": utxos,
            })

        @app.route("/api/mempool")
        def get_mempool():
            return jsonify({"pending": [tx.to_dict() for tx in self.chain.mempool]})

        @app.route("/api/validate")
        def validate():
            ok, msg, work = validate_chain(self.chain.chain)
            return jsonify({"valid": ok, "message": msg, "total_work": work})

        @app.route("/api/merkle-proof/<tx_id>")
        def merkle_proof_of(tx_id):
            for b in self.chain.chain:
                ids = [t.tx_id for t in b.transactions]
                if tx_id in ids:
                    proof = merkle_proof(ids, ids.index(tx_id))
                    return jsonify({
                        "tx_id": tx_id, "block": b.index,
                        "merkle_root": b.merkle_root, "proof": proof,
                        "verified": verify_proof(b.merkle_root, tx_id, proof),
                    })
            return jsonify({"ok": False, "message": "交易不在链上"}), 404

        # ---- 写入类 ----
        @app.route("/api/transaction", methods=["POST"])
        def post_transaction():
            data = request.get_json(silent=True) or {}
            try:
                tx = Transaction.from_dict(data)
            except Exception:
                return jsonify({"ok": False, "message": "交易格式错误"}), 400
            with self._lock:
                ok, msg = self.chain.add_transaction(tx)
            if ok:
                self._broadcast_tx(tx)
                return jsonify({"ok": True, "message": msg, "tx_id": tx.tx_id})
            return jsonify({"ok": False, "message": msg}), 400

        @app.route("/api/mine", methods=["POST"])
        def mine():
            data = request.get_json(silent=True) or {}
            miner = data.get("miner")
            if not miner:
                return jsonify({"ok": False, "message": "缺少 miner 地址"}), 400
            with self._lock:
                block = self.chain.mine(miner)
                self._persist()
            self._broadcast_block(block)
            return jsonify({"ok": True, "message": f"挖出区块 #{block.index}",
                            "block": block.to_dict()})

        # ---- P2P ----
        @app.route("/api/peers")
        def peers():
            return jsonify({"peers": list(self.peers)})

        @app.route("/api/peer", methods=["POST"])
        def add_peer():
            data = request.get_json(silent=True) or {}
            peer = (data.get("peer") or "").rstrip("/")
            if not peer:
                return jsonify({"ok": False, "message": "缺少 peer"}), 400
            self.peers.add(peer)
            threading.Thread(target=self.sync, daemon=True).start()
            return jsonify({"ok": True, "peers": list(self.peers)})

        @app.route("/api/block", methods=["POST"])
        def receive_block():
            data = request.get_json(silent=True) or {}
            try:
                block = Block.from_dict(data)
            except Exception:
                return jsonify({"ok": False, "message": "区块格式错误"}), 400
            with self._lock:
                if any(b.hash == block.hash for b in self.chain.chain):
                    return jsonify({"ok": True, "message": "已知区块"})
                if block.index == len(self.chain.chain) and \
                        block.previous_hash == self.chain.latest_block.hash:
                    candidate = self.chain.chain + [block]
                    ok, msg, _ = validate_chain(candidate)
                    if ok:
                        self.chain.chain.append(block)
                        self.chain._invalidate_utxo()
                        self._persist()
                        self._broadcast_block(block)
                        return jsonify({"ok": True, "message": "已接入新区块"})
                    return jsonify({"ok": False, "message": msg}), 400
                if block.index > len(self.chain.chain):
                    threading.Thread(target=self.sync, daemon=True).start()
                    return jsonify({"ok": False, "message": "落后，触发同步"})
                return jsonify({"ok": False, "message": "旧区块或分叉，忽略"})

        @app.route("/api/tx", methods=["POST"])
        def receive_tx():
            data = request.get_json(silent=True) or {}
            try:
                tx = Transaction.from_dict(data)
            except Exception:
                return jsonify({"ok": False, "message": "交易格式错误"}), 400
            with self._lock:
                ok, msg = self.chain.add_transaction(tx)
            if ok:
                self._broadcast_tx(tx)
                return jsonify({"ok": True, "message": msg})
            return jsonify({"ok": False, "message": msg}), 400

        return app

    # ---------------- 工具 ----------------
    def _subsidy(self):
        from .chain import block_subsidy
        return block_subsidy(self.chain.height + 1)

    # ---------------- 启动 ----------------
    def run(self, host=None, port=None):
        if self.mine_flag:
            if not self.miner_address:
                print("[节点] 开启挖矿需要 --miner 地址")
            else:
                threading.Thread(target=self._mine_loop, daemon=True).start()
        threading.Thread(target=self._sync_loop, daemon=True).start()
        self.app.run(host=host or config.HOST, port=port or self.port, threaded=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="vcoin P2P 链节点")
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--host", default=config.HOST)
    parser.add_argument("--data", default=None, help="数据目录")
    parser.add_argument("--peer", action="append", default=[], help="邻居节点 URL，可多次指定")
    parser.add_argument("--mine", action="store_true", help="后台持续挖矿")
    parser.add_argument("--miner", default=None, help="挖矿奖励地址")
    args = parser.parse_args()

    data_dir = args.data or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", f"node-{args.port}")

    node = Node(data_dir, args.port, peers=args.peer,
                mine=args.mine, miner_address=args.miner)
    print("=" * 60)
    print(f"  {config.COIN_NAME}（{config.COIN_SYMBOL}）P2P 节点")
    print(f"  监听 http://{args.host}:{args.port}  数据目录 {data_dir}")
    print(f"  邻居节点：{list(node.peers) or '无'}")
    print("=" * 60)
    node.run(args.host, args.port)


if __name__ == "__main__":
    main()
