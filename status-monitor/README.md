# status.伏虎.cc · 站点监控台

> 部署在笔记本（192.168.18.67）上，经 cloudflared 隧道 + Cloudflare 暴露为 `status.伏虎.cc`

## 架构

```
浏览器 → status.伏虎.cc (Cloudflare)
       → 隧道 348a8381-e59f-4d2a-86ff-98768cd3a9c4
       → cloudflared（笔记本）
       → 127.0.0.1:8899
       → status_server.py
```

## 文件

| 位置 | 说明 |
| --- | --- |
| `C:\Users\ciallo0721_cmd\fuhu-status\status_server.py` | 服务本体（纯标准库，Python 3.9+） |
| `~/.cloudflared/config.yml` | 隧道 ingress 配置（含 nas + status 两条） |
| `Startup\fuhu-status.bat` | 开机自启监控服务 |
| `Startup\fuhu-tunnel.bat` | 开机自启隧道 |

## 监控项

对每个站点检测：HTTP 状态码、响应时间、TLS 证书剩余天数、ping 延迟与丢包率、页面截图。

| 站点 | 地址 |
| --- | --- |
| 伏虎.cc | https://xn--voqu06k.cc/ |
| 个人主站 | https://ciallo0721-cmd.top/ |
| 塔菲应援站 | https://xn--d6qr7hrtcb06avk0aljka.top/ |
| MiniNAS | https://nas.ciallo0721-cmd.top/ |
| 监控台 | https://status.xn--voqu06k.cc/ |

## 接口

- `GET /` — 监控面板
- `GET /api/status` — JSON 全量数据
- `POST /api/shot/{id}` — 立即重新截图
- `GET /shot/{id}.png` — 截图文件

巡检间隔 60 秒，截图自动间隔 15 分钟。

## 手动启停

```bat
:: 启动监控服务
start "" /min "%LOCALAPPDATA%\Programs\Python\Python39\pythonw.exe" "C:\Users\ciallo0721_cmd\fuhu-status\status_server.py"

:: 启动隧道
cd /d "C:\Users\ciallo0721_cmd\Desktop\新建文件夹\MiniNAS"
cloudflared.exe --config "C:\Users\ciallo0721_cmd\.cloudflared\config.yml" tunnel run
```

停服务：任务管理器结束对应 python / cloudflared 进程。

## 已知坑

1. **必须用 `wmic process call create` 启动**，`start /b` 和 `Start-Process` 起的进程会随 SSH 会话一起被回收。
2. **远程执行带中文路径的命令要用 GBK 编码的 .bat**：cmd 按 GBK 解析，UTF-8 会找不到路径。
3. **取证书不能用 `ssl.get_server_certificate`**：它不发送 ALPN，会被本机的 Watt Toolkit 网络加速器拒绝握手。改用 `http.client` 建连后从 `conn.sock.getpeercert(binary_form=True)` 取。
4. **`ssl.CERT_NONE` 下 `getpeercert()` 返回空字典**，要拿证书详情必须走 PEM + `ssl._ssl._test_decode_cert()`。
5. `cert.pem` 里的 API Token 只对它登录时的那个 zone 有效，无法给后来新增的域名建 DNS 记录。
