#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
伏虎 · 站点监控台 (FuHu Status Monitor)
纯标准库实现，兼容 Python 3.8+
监听 127.0.0.1:8899，由 cloudflared 隧道暴露为 status.伏虎.cc
"""

import json
import os
import re
import ssl
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import urllib.parse
import http.client
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ==================== 配置 ====================

PORT = 8899
BIND = "0.0.0.0"
CHECK_INTERVAL = 60
SHOT_INTERVAL = 900
PING_COUNT = 4
HTTP_TIMEOUT = 12

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHOT_DIR = os.path.join(BASE_DIR, "shots")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

SITES = [
    {"id": "fuhu",   "name": "伏虎.cc",    "url": "https://xn--voqu06k.cc/",
     "host": "xn--voqu06k.cc",              "ping": "xn--voqu06k.cc"},
    {"id": "main",   "name": "个人主站",    "url": "https://ciallo0721-cmd.top/",
     "host": "ciallo0721-cmd.top",          "ping": "ciallo0721-cmd.top"},
    {"id": "taffy",  "name": "塔菲应援站",  "url": "https://xn--d6qr7hrtcb06avk0aljka.top/",
     "host": "xn--d6qr7hrtcb06avk0aljka.top", "ping": "xn--d6qr7hrtcb06avk0aljka.top"},
    {"id": "nas",    "name": "MiniNAS",     "url": "https://nas.ciallo0721-cmd.top/",
     "host": "nas.ciallo0721-cmd.top",      "ping": "192.168.18.67"},
    {"id": "status", "name": "监控台",      "url": "https://status.xn--voqu06k.cc/",
     "host": "status.xn--voqu06k.cc",       "ping": "192.168.18.67"},
]

# ==================== 全局状态 ====================

LOCK = threading.Lock()
STATE = {
    "started": time.time(),
    "updated": 0,
    "checking": False,
    "sites": {},
}
for _s in SITES:
    STATE["sites"][_s["id"]] = {
        "id": _s["id"], "name": _s["name"], "url": _s["url"],
        "up": None, "code": None, "rt": None, "err": "",
        "tls_days": None, "tls_expire": "",
        "ping": None, "loss": None,
        "checked": "", "ts": 0,
        "shot_ts": 0,
    }


LOG_FILE = os.path.join(BASE_DIR, "status.log")


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    except Exception:
        pass


# ==================== 检测逻辑 ====================

def _parse_cert_pem(pem):
    """从 PEM 解析出 (剩余天数, 到期日)"""
    tmp = os.path.join(BASE_DIR, "_cert_tmp.pem")
    try:
        with open(tmp, "w") as f:
            f.write(pem)
        info = ssl._ssl._test_decode_cert(tmp)
        exp = info.get("notAfter")
        if not exp:
            return None, ""
        dt = datetime.strptime(exp, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        return (dt - datetime.now(timezone.utc)).days, dt.strftime("%Y-%m-%d")
    except Exception:
        return None, ""
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


def check_http(url):
    """返回 (ok, code, rt_ms, err, tls_days, tls_expire)

    用 http.client 手动建连：既能拿响应，也能从同一个 TLS 连接里取证书。
    （ssl.get_server_certificate 不发送 ALPN，在本机被网络加速器拒绝握手）
    """
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname
    is_https = parts.scheme == "https"
    port = parts.port or (443 if is_https else 80)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query

    t0 = time.time()
    conn = None
    try:
        if is_https:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.set_alpn_protocols(["http/1.1"])
            conn = http.client.HTTPSConnection(host, port, timeout=HTTP_TIMEOUT, context=ctx)
        else:
            conn = http.client.HTTPConnection(host, port, timeout=HTTP_TIMEOUT)

        conn.request("GET", path, headers={
            "User-Agent": "Mozilla/5.0 (FuHu-Status-Monitor/1.0)",
            "Accept": "*/*",
            "Cache-Control": "no-cache",
        })
        resp = conn.getresponse()
        resp.read(4096)
        rt = round((time.time() - t0) * 1000, 1)
        code = resp.status

        days, expire = None, ""
        if is_https and conn.sock is not None:
            try:
                der = conn.sock.getpeercert(binary_form=True)
                if der:
                    days, expire = _parse_cert_pem(ssl.DER_cert_to_PEM_cert(der))
            except Exception:
                pass

        return (200 <= code < 400), code, rt, "", days, expire
    except Exception as e:
        rt = round((time.time() - t0) * 1000, 1)
        return False, None, rt, str(e)[:80], None, ""
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def check_ping(host):
    """返回 (平均延迟ms, 丢包率%)"""
    try:
        out = subprocess.run(
            ["ping", "-n", str(PING_COUNT), "-w", "2000", host],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=PING_COUNT * 3 + 6,
        ).stdout.decode("gbk", "ignore")
    except Exception:
        return None, None
    loss = None
    m = re.search(r"\((\d+)%", out)
    if m:
        loss = int(m.group(1))
    avg = None
    if loss == 100:
        avg = None
    else:
        m = re.search(r"=\s*(\d+)ms[，,]\s*最长\s*=\s*(\d+)ms[，,]\s*平均\s*=\s*(\d+)ms", out)
        if m:
            avg = float(m.group(3))
        else:
            m = re.search(r"Average = (\d+)ms", out)
            if m:
                avg = float(m.group(1))
    return avg, loss


def take_shot(site):
    """用 Edge headless 截图"""
    if not os.path.exists(EDGE):
        return False, "未找到 Edge"
    if not os.path.isdir(SHOT_DIR):
        try:
            os.makedirs(SHOT_DIR)
        except Exception:
            pass
    out_path = os.path.join(SHOT_DIR, site["id"] + ".png")
    tmp_profile = os.path.join(SHOT_DIR, "profile_" + site["id"])
    cmd = [
        EDGE,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--user-data-dir=" + tmp_profile,
        "--window-size=1440,900",
        "--virtual-time-budget=9000",
        "--screenshot=" + out_path,
        site["url"],
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    except Exception as e:
        return False, str(e)[:60]
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1200:
        return True, ""
    return False, "截图未生成"


def check_one(site):
    sid = site["id"]
    now = datetime.now()
    ok, code, rt, err, days, expire = check_http(site["url"])
    avg, loss = check_ping(site["ping"])

    with LOCK:
        st = STATE["sites"][sid]
        st.update({
            "up": ok, "code": code, "rt": rt, "err": err,
            "tls_days": days, "tls_expire": expire,
            "ping": avg, "loss": loss,
            "checked": now.strftime("%H:%M:%S"), "ts": time.time(),
        })


def check_all():
    with LOCK:
        if STATE["checking"]:
            return
        STATE["checking"] = True
    try:
        for site in SITES:
            try:
                check_one(site)
            except Exception as e:
                log("检查 %s 异常: %s" % (site["id"], e))
        with LOCK:
            STATE["updated"] = time.time()
        log("巡检完成")
    finally:
        with LOCK:
            STATE["checking"] = False


def background_loop():
    time.sleep(1)
    check_all()
    last_shot = 0
    while True:
        time.sleep(CHECK_INTERVAL)
        check_all()
        if time.time() - last_shot > SHOT_INTERVAL:
            last_shot = time.time()
            for site in SITES:
                try:
                    ok, msg = take_shot(site)
                    if ok:
                        with LOCK:
                            STATE["sites"][site["id"]]["shot_ts"] = time.time()
                    else:
                        log("截图 %s 失败: %s" % (site["id"], msg))
                except Exception as e:
                    log("截图 %s 异常: %s" % (site["id"], e))


# ==================== 页面 ====================

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>伏虎 · 监控台</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--gold:#e8b04b;--gold2:#ffd98a;--ok:#22c55e;--bad:#ef4444;--warn:#f59e0b;--ink:#f4efe4;--dim:#9c9488;--line:rgba(232,176,75,.18)}
body{background:#06060a;color:var(--ink);font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif;line-height:1.7;min-height:100vh;padding:0 0 60px}
body::before{content:"";position:fixed;inset:0;z-index:-1;background:radial-gradient(38% 32% at 15% 8%,rgba(194,65,12,.24),transparent 66%),radial-gradient(34% 30% at 86% 16%,rgba(232,176,75,.16),transparent 68%),radial-gradient(46% 40% at 50% 110%,rgba(120,53,15,.28),transparent 72%)}
.wrap{max-width:1180px;margin:0 auto;padding:0 22px}
header{padding:34px 0 22px;border-bottom:1px solid rgba(255,255,255,.06);display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.seal{width:46px;height:46px;border:2px solid rgba(194,65,12,.85);border-radius:11px;display:grid;place-items:center;font-family:"Songti SC",serif;font-size:17px;font-weight:700;color:#f0563a;transform:rotate(-8deg);box-shadow:0 0 22px rgba(194,65,12,.3)}
h1{font-family:"Songti SC",serif;font-size:23px;letter-spacing:.16em;font-weight:700}
.sub{font-size:11px;letter-spacing:.3em;color:#615a4f;font-family:Consolas,monospace}
.sum{margin-left:auto;display:flex;gap:22px;align-items:center;flex-wrap:wrap}
.big{font-family:Consolas,monospace;font-size:26px;font-weight:700;color:var(--gold2);text-shadow:0 0 22px rgba(232,176,75,.35)}
.big.bad{color:var(--bad);text-shadow:0 0 22px rgba(239,68,68,.35)}
.lab{font-size:10.5px;letter-spacing:.2em;color:#615a4f;font-family:Consolas,monospace}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px;margin-top:26px}
.card{border:1px solid var(--line);border-radius:18px;background:rgba(255,255,255,.04);overflow:hidden;backdrop-filter:blur(12px);transition:transform .3s,border-color .3s}
.card:hover{transform:translateY(-3px);border-color:rgba(232,176,75,.4)}
.chead{padding:18px 20px 14px;display:flex;align-items:center;gap:12px;border-bottom:1px solid rgba(255,255,255,.05)}
.dot{width:10px;height:10px;border-radius:50%;background:#444;flex:0 0 auto}
.dot.up{background:var(--ok);box-shadow:0 0 14px var(--ok);animation:pulse 2s infinite}
.dot.down{background:var(--bad);box-shadow:0 0 14px var(--bad);animation:pulse 1s infinite}
.dot.wait{background:var(--warn);box-shadow:0 0 14px var(--warn);animation:pulse 1.4s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.cname{font-family:"Songti SC",serif;font-size:16px;font-weight:700;letter-spacing:.1em}
.curl{font-size:11px;color:#6f6759;font-family:Consolas,monospace;margin-top:2px;word-break:break-all}
.badge{margin-left:auto;font-family:Consolas,monospace;font-size:11px;letter-spacing:.1em;padding:4px 12px;border-radius:999px;border:1px solid var(--line)}
.badge.up{color:var(--ok);border-color:rgba(34,197,94,.4)}
.badge.down{color:var(--bad);border-color:rgba(239,68,68,.4)}
.badge.wait{color:var(--warn);border-color:rgba(245,158,11,.4)}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:rgba(255,255,255,.05)}
.m{background:#0a0a0e;padding:13px 10px;text-align:center}
.mv{font-family:Consolas,monospace;font-size:17px;font-weight:700;color:var(--gold2)}
.mv.na{color:#4a453c;font-size:15px}
.mk{font-size:9.5px;letter-spacing:.16em;color:#615a4f;font-family:Consolas,monospace;margin-top:3px}
.shot{position:relative;background:#08080b;height:190px;overflow:hidden;border-top:1px solid rgba(255,255,255,.05)}
.shot img{width:100%;height:100%;object-fit:cover;object-position:top center;display:block;transition:transform .5s}
.shot:hover img{transform:scale(1.04)}
.shot .ph{position:absolute;inset:0;display:grid;place-items:center;color:#4a453c;font-size:11.5px;font-family:Consolas,monospace;letter-spacing:.12em}
.shot .ts{position:absolute;right:8px;bottom:8px;background:rgba(0,0,0,.72);color:var(--gold);font-size:10px;font-family:Consolas,monospace;padding:3px 9px;border-radius:6px;letter-spacing:.06em}
.refresh{position:absolute;left:8px;bottom:8px;background:rgba(0,0,0,.72);border:1px solid var(--line);color:var(--gold2);font-size:11px;padding:4px 11px;border-radius:7px;cursor:pointer;font-family:Consolas,monospace;letter-spacing:.08em}
.refresh:hover{background:rgba(232,176,75,.16)}
footer{margin-top:40px;padding-top:22px;border-top:1px solid rgba(255,255,255,.05);display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;font-size:11.5px;color:#615a4f;font-family:Consolas,monospace}
footer a{color:var(--dim);text-decoration:none}
footer a:hover{color:var(--gold)}
@media(max-width:560px){.metrics{grid-template-columns:repeat(2,1fr)}.sum{margin-left:0;width:100%}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="seal">伏虎</div>
    <div>
      <h1>伏虎 · 监控台</h1>
      <div class="sub">STATUS MONITOR</div>
    </div>
    <div class="sum">
      <div style="text-align:center">
        <div class="big" id="up-count">--</div>
        <div class="lab">ONLINE</div>
      </div>
      <div style="text-align:center">
        <div class="big" id="tot-count">--</div>
        <div class="lab">TOTAL</div>
      </div>
      <div style="text-align:center">
        <div class="big" id="up-time" style="font-size:17px">--</div>
        <div class="lab">UPTIME</div>
      </div>
    </div>
  </header>
  <div class="grid" id="grid"></div>
  <footer>
    <span>status.xn--voqu06k.cc &nbsp;·&nbsp; <span id="updated">等待首次巡检…</span></span>
    <span>Powered by MiniNAS &amp; cloudflared &nbsp;·&nbsp; <a href="https://xn--voqu06k.cc/" target="_blank">伏虎.cc</a></span>
  </footer>
</div>
<script>
var SITE_IDS = null;
function fmtTime(ts){
  if(!ts) return "";
  var d = new Date(ts*1000);
  var p = function(n){return n<10?"0"+n:n;};
  return p(d.getHours())+":"+p(d.getMinutes())+":"+p(d.getSeconds());
}
function fmtDur(sec){
  sec = Math.floor(sec);
  var d = Math.floor(sec/86400), h = Math.floor(sec%86400/3600), m = Math.floor(sec%3600/60);
  if(d>0) return d+"d "+h+"h";
  if(h>0) return h+"h "+m+"m";
  return m+"m";
}
function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];}); }
function val(v,suffix,dec){
  if(v===null||v===undefined) return '<div class="mv na">--</div>';
  var n = dec===undefined ? v : Number(v).toFixed(dec);
  return '<div class="mv">'+n+(suffix||"")+'</div>';
}
function render(data){
  var grid = document.getElementById("grid");
  var ids = Object.keys(data.sites);
  if(!SITE_IDS){
    SITE_IDS = ids;
    grid.innerHTML = ids.map(function(id){
      var s = data.sites[id];
      return '<div class="card" data-id="'+id+'">'
        + '<div class="chead">'
        +   '<span class="dot" id="d-'+id+'"></span>'
        +   '<div style="min-width:0"><div class="cname">'+esc(s.name)+'</div>'
        +   '<div class="curl">'+esc(s.url)+'</div></div>'
        +   '<span class="badge" id="b-'+id+'">--</span>'
        + '</div>'
        + '<div class="metrics">'
        +   '<div class="m"><div id="code-'+id+'"><div class="mv na">--</div></div><div class="mk">STATUS</div></div>'
        +   '<div class="m"><div id="rt-'+id+'"><div class="mv na">--</div></div><div class="mk">HTTP</div></div>'
        +   '<div class="m"><div id="pg-'+id+'"><div class="mv na">--</div></div><div class="mk">PING</div></div>'
        +   '<div class="m"><div id="tls-'+id+'"><div class="mv na">--</div></div><div class="mk">TLS</div></div>'
        + '</div>'
        + '<div class="shot">'
        +   '<img id="img-'+id+'" src="/shot/'+id+'.png?t='+Date.now()+'" alt="" style="display:none" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'grid\'">'
        +   '<div class="ph" id="ph-'+id+'">暂无截图</div>'
        +   '<button class="refresh" data-shot="'+id+'">重新截图</button>'
        +   '<span class="ts" id="ts-'+id+'"></span>'
        + '</div>'
        + '</div>';
    }).join("");
    grid.addEventListener("click", function(e){
      var btn = e.target.closest("[data-shot]");
      if(btn){
        var id = btn.getAttribute("data-shot");
        btn.textContent = "截图中…";
        fetch("/api/shot/" + id, {method:"POST"}).then(function(){ return r; }).catch(function(){});
        setTimeout(function(){ reloadShot(id); btn.textContent = "重新截图"; }, 6000);
      }
    });
  }
  var up = 0;
  ids.forEach(function(id){
    var s = data.sites[id];
    var known = s.up !== null;
    if(s.up) up++;
    var cls = !known ? "wait" : (s.up ? "up" : "down");
    var d = document.getElementById("d-"+id);
    var b = document.getElementById("b-"+id);
    if(d) d.className = "dot " + cls;
    if(b){ b.className = "badge " + cls; b.textContent = !known ? "检测中" : (s.up ? "在线" : "离线"); }
    var c = document.getElementById("code-"+id);
    if(c) c.innerHTML = (s.code===null||s.code===undefined) ? '<div class="mv na">--</div>' : '<div class="mv">'+s.code+'</div>';
    var r = document.getElementById("rt-"+id);
    if(r) r.innerHTML = val(s.rt, "ms") ;
    var p = document.getElementById("pg-"+id);
    if(p) p.innerHTML = (s.ping===null||s.ping===undefined) ? '<div class="mv na">--</div>' : '<div class="mv">'+Math.round(s.ping)+'ms</div>';
    var t = document.getElementById("tls-"+id);
    if(t) t.innerHTML = (s.tls_days===null||s.tls_days===undefined) ? '<div class="mv na">--</div>' : '<div class="mv">'+s.tls_days+'d</div>';
    var ts = document.getElementById("ts-"+id);
    if(ts) ts.textContent = s.shot_ts ? fmtTime(s.shot_ts) : "";
  });
  document.getElementById("up-count").textContent = up;
  document.getElementById("up-count").className = "big" + (up === ids.length ? "" : " bad");
  document.getElementById("tot-count").textContent = ids.length;
  document.getElementById("updated").textContent = "更新于 " + fmtTime(data.updated) + " · 运行 " + fmtDur(data.uptime);
}
function reloadShot(id){
  var img = document.getElementById("img-"+id);
  var ph = document.getElementById("ph-"+id);
  if(!img) return;
  img.style.display = "none";
  img.src = "/shot/" + id + ".png?t=" + Date.now();
  img.onload = function(){ img.style.display = "block"; if(ph) ph.style.display = "none"; };
}
function tick(){
  fetch("/api/status", {cache:"no-store"})
    .then(function(r){ return r.json(); })
    .then(render)
    .catch(function(){});
}
tick();
setInterval(tick, 10000);
</script>
</body>
</html>
"""


# ==================== HTTP 服务 ====================

class Handler(BaseHTTPRequestHandler):
    server_version = "FuHuStatus/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        path = self.path.split("?")[0]

        if path in ("/", "/index.html"):
            return self._send(200, PAGE)

        if path == "/api/status":
            with LOCK:
                payload = {
                    "updated": STATE["updated"],
                    "uptime": time.time() - STATE["started"],
                    "sites": STATE["sites"],
                }
            return self._send(200, json.dumps(payload, ensure_ascii=False),
                              "application/json; charset=utf-8")

        if path.startswith("/shot/"):
            sid = path[6:].replace(".png", "")
            if not re.match(r"^[a-z0-9_-]+$", sid):
                return self._send(400, "bad id")
            fp = os.path.join(SHOT_DIR, sid + ".png")
            if os.path.exists(fp):
                try:
                    with open(fp, "rb") as f:
                        data = f.read()
                    return self._send(200, data, "image/png")
                except Exception:
                    return self._send(500, "read error")
            return self._send(404, "no shot")

        return self._send(404, "not found")

    def do_POST(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/shot/"):
            sid = path[10:]
            site = None
            for s in SITES:
                if s["id"] == sid:
                    site = s
                    break
            if not site:
                return self._send(404, "no such site")

            def job():
                ok, msg = take_shot(site)
                if ok:
                    with LOCK:
                        STATE["sites"][sid]["shot_ts"] = time.time()
                    log("手动截图 %s 完成" % sid)
                else:
                    log("手动截图 %s 失败: %s" % (sid, msg))

            threading.Thread(target=job, daemon=True).start()
            return self._send(202, json.dumps({"ok": True, "msg": "started"}),
                              "application/json; charset=utf-8")
        return self._send(404, "not found")


def main():
    if not os.path.isdir(SHOT_DIR):
        try:
            os.makedirs(SHOT_DIR)
        except Exception:
            pass

    log("=" * 52)
    log("伏虎 · 站点监控台 启动")
    log("监听 %s:%d   巡检间隔 %ds" % (BIND, PORT, CHECK_INTERVAL))
    log("监控站点 %d 个" % len(SITES))
    log("=" * 52)

    t = threading.Thread(target=background_loop, daemon=True)
    t.start()

    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("已停止")


if __name__ == "__main__":
    main()
