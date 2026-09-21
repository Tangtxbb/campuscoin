# 部署到阿里云服务器（从局域网到公网）

把 CAMP 节点部署到一台有公网 IP 的云服务器上，你的链就从「局域网玩具」变成「任何地方都能接入的公链」。核心原理：节点只是一个监听 `0.0.0.0:8000` 的 Python 服务，放到公网服务器上，全世界任何节点都能连它。

## 一、和局域网的本质区别

| | 局域网 | 公网（云服务器） |
| --- | --- | --- |
| 节点地址 | 内网 IP，如 `192.168.1.100` | 公网 IP，如 `47.99.123.45` |
| 谁能连 | 同一 WiFi 的电脑 | 互联网上任何设备 |
| 节点发现 | UDP 广播（`--discover`） | 用 `--peer` 手动指定公网 IP |
| 角色 | 对等节点 | 可当「种子节点」，别人连它入网 |

> UDP 自动发现只在局域网内有效（广播不跨公网）。公网场景下，把云服务器的公网 IP 当作种子地址，其它节点用 `--peer` 连它。

## 二、阿里云 ECS 部署步骤

1. **买服务器**：最便宜的 1 核 1G（Ubuntu 20.04/22.04）就够。
2. **开放端口**：阿里云控制台 → 安全组 → 添加入方向规则，放行 **TCP 8000**（UDP 5333 跨公网用不上，可不放）。
3. **上传代码**（二选一）：
   ```bash
   # 方式 A：git 克隆（你的 GitHub 仓库）
   git clone https://github.com/Tangtxbb/campuscoin.git
   # 方式 B：本地打包上传
   scp -r D:/区块链学术研究 root@<公网IP>:/root/campuscoin
   ```
4. **装依赖并启动**：
   ```bash
   cd campuscoin
   pip install -r requirements.txt
   python -m vcoin.node --host 0.0.0.0 --port 8000
   ```
5. **验证**：浏览器打开 `http://<公网IP>:8000`，能看到区块浏览器即成功。

## 三、用 Docker 一键部署（推荐）

```bash
cd campuscoin
docker build -t campuscoin .
docker run -d --name campuscoin -p 8000:8000 --restart unless-stopped campuscoin
```

## 四、让本地电脑连上公网节点

```bash
# 本地电脑（任何网络）运行：
python -m vcoin.node --port 8000 --peer http://<公网IP>:8000
# 或者只当矿工：
python scripts/miner.py --node http://<公网IP>:8000
```

## 五、注意事项

- **安全**：节点 API 没有鉴权，公网开放后任何人都能查询/挖矿。建议：
  - 安全组把 8000 端口限制为「只允许你自己的 IP」；
  - 或给 API 加个简单的 token 校验（可后续实现）。
- **持久化**：链数据存在服务器 `data/node-8000/chain.json`，重启不丢。
- **后台运行**：正式用建议 `nohup` / `tmux` / `systemd`，或 Docker 的 `--restart unless-stopped`。
