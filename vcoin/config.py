# -*- coding: utf-8 -*-
"""
全局配置：代币经济、挖矿、P2P 网络等参数集中在这里。

与真实公链的对照（便于理解）：
- COIN / DECIMALS      —— 类似比特币的"聪"：链上金额一律用整数最小单位存储，避免浮点误差。
- HALVING_INTERVAL     —— 比特币是 210000 个区块减半一次；这里改成 100 便于观察。
- TOTAL_SUPPLY         —— 比特币总量 2100 万；这里设 1 万币作为教学上限。
- DIFFICULTY_ADJUST    —— 比特币每 2016 块调整一次；这里每 10 块。
"""

# ---------------- 代币与单位 ----------------
COIN_NAME = "校园币"
COIN_SYMBOL = "CAMP"
COIN = 10 ** 8                      # 1 币 = 1 亿最小单位（类似"聪"）
DECIMALS = 8


def fmt(amount) -> str:
    """把最小单位整数格式化为人类可读的币数量，如 123456789 -> '1.23456789'"""
    neg = amount < 0
    a = abs(int(amount))
    whole, frac = divmod(a, COIN)
    s = f"{whole}.{frac:0{DECIMALS}d}".rstrip("0").rstrip(".")
    return ("-" if neg else "") + s


# ---------------- 经济模型（减半 + 总量上限） ----------------
INITIAL_REWARD = 50 * COIN          # 初始区块奖励 = 50 币
HALVING_INTERVAL = 100              # 每 100 个区块奖励减半（比特币 = 210000）
TOTAL_SUPPLY = 10_000 * COIN        # 总量上限 = 1 万币（比特币 = 2100 万）
MIN_FEE = 0                         # 最低手续费（最小单位），0 = 不强制

# ---------------- 挖矿与难度 ----------------
INITIAL_DIFFICULTY = 2              # 初始难度（哈希前导 0 的个数）
MAX_DIFFICULTY = 5                  # 难度上限（教学用，避免难度 16 倍跃升后无法出块）
DIFFICULTY_ADJUST_INTERVAL = 10     # 每 10 个区块调整一次难度
BLOCK_TIME_TARGET = 10              # 目标出块时间（秒）
MAX_TX_PER_BLOCK = 10               # 每块最多打包的交易数

# ---------------- P2P 网络 ----------------
HOST = "0.0.0.0"                    # 监听地址；0.0.0.0 允许局域网访问
PORT = 8000                         # 服务端口
SYNC_INTERVAL = 5                   # 定时与邻居同步的间隔（秒）

# ---------------- 系统地址 ----------------
SYSTEM_ADDRESS = "0" * 40           # coinbase 的"发送方"
