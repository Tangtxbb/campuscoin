# 校园币（CAMP）· 一条能跑起来的迷你公链

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/%E7%8A%B6%E6%80%81-%E5%AD%A6%E4%B9%A0%E9%A1%B9%E7%9B%AE-lightgrey)

一个用 **Python 从零实现**、用于**学习区块链原理**的迷你公链。它不是玩具 demo，而是复刻了比特币/以太坊的核心机制，让每一条原理都能"跑起来"亲眼验证：

- 用 **ECDSA** 签名转账、用 **UTXO** 记账、防双花、收手续费
- 用 **PoW** 挖矿、**256 位目标值难度自动调整**、**奖励减半**、**总量上限**
- 多节点 **P2P 组网**、**UDP 自动发现邻居**、**最长链（最重链）共识**
- **Merkle 树** + **SPV 轻验证**、**完整 BIP32 HD 钱包**
- **最小智能合约**（多重签名、时间锁）、**网页区块浏览器**

**两台电脑连上同一个局域网，就能组一条真正去中心化的链**——没有中心服务器，每个节点各自存链、独立验证、竞争出块。

> 仅供技术研究与学习，币无任何真实价值。

---

## 一、和正规币（比特币/以太坊）的对照

| 机制 | 本项目的实现 | 真实公链 |
| --- | --- | --- |
| 账户模型 | UTXO（输入引用未花费输出） | 比特币 = UTXO，以太坊 = 账户+状态树 |
| 交易签名 | secp256k1 逐输入签名 | 同款曲线 |
| 手续费 | 输入总额 − 输出总额 = 手续费给矿工 | 比特币矿工费 / 以太坊 Gas |
| 区块结构 | 区块头(含 Merkle 根) + 区块体 | 完全一致 |
| PoW | 256 位目标值 | 比特币 256 位目标值（同款） |
| 难度调整 | 每 10 块调整一次 | 比特币每 2016 块 |
| 减半 | 每 100 块减半 | 比特币每 210000 块 |
| 总量 | 1 万币上限 | 比特币 2100 万 |
| 钱包 | BIP39 助记词 | BIP32/39/44 标准 |
| 共识 | 最重链（累计工作量） | Nakamoto 最长链 |
| 网络 | HTTP P2P 广播 + 同步 | TCP gossip 协议 |

> 已实现一个**最小智能合约脚本 VM**（多签、时间锁），但**完整 EVM + Solidity 编译器**工程体量巨大，不在本项目范围。

---

## 二、目录结构

```
区块链学术研究/
├── vcoin/
│   ├── config.py         # 代币经济、难度、P2P 参数（都可改）
│   ├── wallet.py         # Wallet + HDWallet（BIP39 助记词）
│   ├── transaction.py    # UTXO：TxIn / TxOut / Transaction
│   ├── block.py          # 区块头 + 区块体 + PoW
│   ├── merkle.py         # Merkle 树与 SPV 证明
│   ├── script.py         # 最小智能合约脚本 VM（多签 + 时间锁）
│   ├── chain.py          # UTXO 集合、减半、难度调整、整链校验
│   ├── node.py           # P2P 节点（广播 + 同步 + 共识）
│   └── explorer.html     # 网页区块浏览器
├── scripts/
│   ├── cli.py            # 命令行工具
│   └── miner.py          # 矿工客户端
├── tests/                # 16 个单元测试（含智能合约）
└── requirements.txt
```

---

## 三、安装

```bash
cd D:/区块链学术研究
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt       # flask, ecdsa, requests, mnemonic
```

---

## 四、单节点快速体验

```bash
python -m vcoin.node                   # 启动节点，监听 8000
```

浏览器打开 `http://127.0.0.1:8000` 就是区块浏览器。

另开终端：

```bash
python scripts/cli.py new-hd-wallet --file alice.json   # 生成助记词钱包（记下助记词！）
python scripts/cli.py mine --miner <地址>                # 挖矿，得 50 币
python scripts/cli.py balance <地址>                     # 查余额
python scripts/cli.py send --from alice.json --to <对方地址> --amount 10 --fee 0.001
python scripts/cli.py mine --miner <地址>                # 再挖一块，把转账打包上链
python scripts/cli.py validate                           # 校验整条链
python scripts/cli.py merkle-proof <交易ID>              # 看一笔交易的 SPV 证明
```

> `new-hd-wallet` 生成的助记词能派生无穷多个地址；`new-wallet` 生成单个私钥钱包。

---

## 五、多节点 P2P（真正的去中心化）

**每个节点都持有整条链，没有中心。** 在两台电脑（同一局域网）上分别运行：

```bash
# 电脑 A
python -m vcoin.node --port 8000 --peer http://<电脑B的IP>:8000 --mine --miner <A的地址>

# 电脑 B
python -m vcoin.node --port 8000 --peer http://<电脑A的IP>:8000 --mine --miner <B的地址>
```

- `--peer` 指定邻居，两台互相指对方；或加 `--discover` 用 UDP 在局域网自动发现邻居。
- `--mine --miner` 让节点后台持续挖矿。
- 任一节点挖出区块都会广播给邻居；收到后各自独立验证，采纳「工作量更大」的链。
- 本机试玩：起两个端口互连即可
  `python -m vcoin.node --port 8000 --peer http://127.0.0.1:8001` 和
  `python -m vcoin.node --port 8001 --peer http://127.0.0.1:8000`。

也可以单独跑矿工客户端（连接任一节点）：

```bash
python scripts/miner.py --node http://192.168.1.100:8000
```

---

## 六、HTTP API 一览（都在 `/api/` 前缀下）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 区块浏览器 |
| GET | `/api/info` | 节点信息 |
| GET | `/api/chain` | 整条链 |
| GET | `/api/block/<index>` | 单区块 |
| GET | `/api/tx/<tx_id>` | 查交易 |
| GET | `/api/address/<addr>` | 余额 + UTXO |
| GET | `/api/mempool` | 交易池 |
| GET | `/api/validate` | 校验链 |
| GET | `/api/merkle-proof/<tx_id>` | SPV 证明 |
| POST | `/api/transaction` | 提交交易（会广播） |
| POST | `/api/mine` | 挖矿（会广播） |
| GET/POST | `/api/peers` `/api/peer` | 邻居管理 |
| POST | `/api/block` `/api/tx` | P2P 接收广播 |

---

## 七、测试

```bash
python -m unittest discover -s tests
```

覆盖：UTXO 转账与找零、防双花、防篡改、Merkle 证明、减半、难度调整、整链校验、智能合约（多签 + 时间锁）、BIP32 派生。

---

## 八、还没做、可以继续的方向

1. **完整的智能合约（EVM + Solidity）**：目前是最小脚本 VM，要做成以太坊那样需要完整虚拟机 + 编译器 + Gas 计量，工程体量巨大。
2. **真正的 TCP P2P**：目前用 HTTP 做广播/同步（已实现 UDP 自动发现），换成 socket gossip 协议属于"管道工程"，学习价值低于上面的共识/数据层。

---

## 九、安全提醒

- 助记词/私钥绝不能泄露，谁拿到谁就能花你的币。
- 本项目为教学实现，请勿用于真实资产或生产环境。
