# 伏虎 · 伏虎.cc

> 降龙伏虎，一网打尽。

「伏虎.cc」的单页站点，纯静态、零依赖、单文件 `index.html`。

## 域名

| 项目 | 值 |
| --- | --- |
| 中文域名 | 伏虎.cc |
| Punycode | `xn--voqu06k.cc` |
| 到期日 | 2027-08-02 |
| 托管 | GitHub Pages |

## 文件

| 文件 | 说明 |
| --- | --- |
| `index.html` | 页面本体（内联 CSS / JS，无外部资源） |
| `CNAME` | GitHub Pages 自定义域名（**必须写 punycode**） |
| `.nojekyll` | 关闭 Jekyll 处理，避免静态资源被吞 |

## 部署

1. 仓库 Settings → Pages → Source 选择 `Deploy from a branch`，分支 `main` / 根目录。
2. DNS 配置（域名服务商处）：
   - A 记录：`185.199.108.153`、`185.199.109.153`、`185.199.110.153`、`185.199.111.153`
   - AAAA 记录：`2606:50c0:8000::153`、`2606:50c0:8001::153`、`2606:50c0:8002::153`、`2606:50c0:8003::153`
   - 或者 CNAME 记录指向 `ciallo0721-cmd.github.io`
3. 等待 DNS 生效后勾选 `Enforce HTTPS`。

## 本地预览

```bash
python -m http.server 8000
```

然后访问 <http://localhost:8000>。

---

© 2026 [ciallo0721-cmd](https://github.com/ciallo0721-cmd)
