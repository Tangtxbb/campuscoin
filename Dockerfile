# 校园币（CAMP）链节点镜像
# 用法：
#   docker build -t campuscoin .
#   docker run -d --name campuscoin -p 8000:8000 campuscoin
#   （然后浏览器打开 http://<服务器公网IP>:8000 就能看到区块浏览器）

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
EXPOSE 5333/udp

# 监听 0.0.0.0，允许外部（公网）访问
CMD ["python", "-m", "vcoin.node", "--host", "0.0.0.0", "--port", "8000"]
