# 伏虎隧道启动器（bat）

笔记本 `192.168.18.67` 上的穿透启动脚本原件存档。笔记本那份丢了，从这儿拷回去即可。

## 文件

| 文件 | 部署位置 | 用途 |
|---|---|---|
| `fuhu-tunnel.bat` | `C:\Users\ciallo0721_cmd\fuhu-status\` | 服务版：无输出，写日志，供开机自启 / 计划任务 / 远程调用 |
| `fuhu-tunnel.bat` | `%APPDATA%\...\Startup\` | 同一份，开机自动拉起隧道 |
| `伏虎穿透.bat` | 桌面 | 手动版：双击重启隧道，带状态检查 |
| `伏虎监控台.bat` | 桌面 | 双击启动监控台（8899） |

## 它们做什么

1. 检查 `cloudflared.exe` 与 `config.yml` 是否存在
2. 结束已有隧道进程（自愈，避免僵尸实例）
3. 以 `/min` 后台拉起隧道
4. 检测 MiniNAS(80) / 监控台(8899) 是否在监听

隧道映射（`~/.cloudflared/config.yml`）：

```
nas.ciallo0721-cmd.top    -> http://localhost:80
status.xn--voqu06k.cc     -> http://localhost:8899
```

## 使用时踩过的坑（重要）

1. **中文路径下 cmd 不可靠** —— `cloudflared.exe` 原本在 `Desktop\新建文件夹\MiniNAS\`，
   `cd /d` 到中文目录会失败，bat 静默退出。现已复制到纯 ASCII 路径
   `C:\Users\ciallo0721_cmd\fuhu-status\cloudflared.exe`，bat 全部改用该路径。
2. **编码规则**（远程通过 OpenSSH 下发时）
   - 命令行参数发 **UTF-8**：OpenSSH 会按 UTF-8 解码再转 UTF-16，发 GBK 必然乱码
   - bat / ps1 等**文件内容写 GBK**：cmd 按系统 ANSI 代码页读取
   - 文件名重命名走 **SFTP rename**（UTF-8），不要用 cmd 的 `ren`
3. **SFTP rename 不覆盖已有文件**，目标存在时先 `sftp.remove`
4. **SSH 会话会被回收** —— `start /b`、`Start-Process` 起的进程随会话一起死；
   改用 `wmic process call create` 创建脱离进程
5. **计划任务 `/tr` 里出现中文路径**会被转成 `???????.bat`，任务必然失败（上次结果=1）——
   路径必须是纯 ASCII
6. bat 里不要用 `timeout`（无控制台时不可用），用 `ping -n N 127.0.0.1 >nul` 代替延时

## 验证

```bat
type C:\Users\ciallo0721_cmd\fuhu-status\launch.log
```

正常输出：

```
[2026/09/14 周一 20:44:34.49] launch
[v] ok
```
