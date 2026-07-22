# 号数账本 · 双色球/大乐透开奖统计工具

一个纯静态网页工具：选彩种、选期数区间，查看该区间内号码出现频率、冷热号、奇偶大小比。
配合 GitHub Actions 定时任务，每天自动抓取官方最新开奖数据。

**重要提醒**：双色球、大乐透每期开奖都是独立随机事件，历史出现频率（冷热号）不会影响、
也不能预测下一期开出的号码。本工具的统计数据仅供了解历史分布，不构成"必中"依据，请理性购彩。

---

## 这套东西是什么结构

```
lottery-ledger/
├── index.html                        # 网页工具本身，托管到 GitHub Pages 后就是你的访问地址
├── data/
│   ├── ssq.json                       # 双色球历史数据(抓取脚本自动生成，首次是空的)
│   └── dlt.json                       # 大乐透历史数据(抓取脚本自动生成，首次是空的)
├── scripts/
│   └── fetch_lottery_data.py          # 抓取脚本：请求官方接口，写入 data/*.json
└── .github/workflows/update-data.yml  # GitHub Actions 配置：每天定时自动跑一次抓取脚本并提交
```

原理很简单：GitHub Actions 每天在云端自动跑一次抓取脚本 → 把最新数据写进 `data/` 目录里的
两个 JSON 文件 → 自动 `git commit + push` 提交这个变化 → 你的网页（托管在 GitHub Pages 上）
打开时会去读这两个 JSON 文件。全程不需要你自己的电脑开机，也不需要服务器。

---

## 部署步骤（跟着做一遍，大概10分钟）

### 1. 创建仓库
1. 登录 GitHub，右上角 `+` → `New repository`
2. 仓库名随意，比如 `lottery-ledger`，选择 **Public**（GitHub Pages 免费版要求公开仓库）
3. 创建好后，把这个文件夹里的所有文件（`index.html`、`data/`、`scripts/`、`.github/`）
   上传到仓库里 —— 最简单的方式是在仓库页面点 `Add file → Upload files`，把整个文件夹拖进去
   （注意要保留 `.github/workflows/update-data.yml` 这个隐藏目录结构，如果网页上传漏了，
   也可以用 `git clone` 到本地后用 `git add . && git commit && git push` 的方式提交）

### 2. 打开 Actions 权限
1. 仓库页面 → `Settings` → `Actions` → `General`
2. 往下翻到 **Workflow permissions**，选择 **Read and write permissions**，保存
   （这一步是必须的，不然 Actions 里的自动提交会因为没权限而失败）

### 3. 手动跑一次抓取，验证是否工作
1. 仓库页面 → `Actions` 标签页 → 左侧选择 "更新彩票开奖数据"
2. 右侧点 `Run workflow` → `Run workflow`（绿色按钮）手动触发一次
3. 等一两分钟，刷新页面看这次运行是绿勾还是红叉
   - **绿勾**：说明抓取成功，`data/ssq.json` 和 `data/dlt.json` 应该已经被自动提交更新了
   - **红叉**：点进去看日志里 `[ERROR]` 那一行的报错信息，大概率是官方接口结构变了，
     需要调整 `scripts/fetch_lottery_data.py` 里的字段解析部分（见下方"如果接口失效了怎么办"）

### 4. 开启 GitHub Pages，拿到访问地址
1. 仓库页面 → `Settings` → `Pages`
2. **Source** 选择 `Deploy from a branch`，Branch 选 `main` / `(root)`，保存
3. 等一两分钟，页面顶部会出现你的网址，形如：
   `https://你的用户名.github.io/lottery-ledger/`
4. 打开这个网址，就是可以分享给朋友的正式工具了

以后每天 GitHub Actions 会在北京时间 23:00 自动跑一次，数据自动更新，你完全不用管。
如果哪天等不及想立刻更新，回到 `Actions` 页面手动点一次 `Run workflow` 就行。

---

## 如果接口失效了怎么办

官方接口（尤其是双色球福彩官网那个）历史上出现过反爬升级的情况，一旦官网调整了接口，
`fetch_lottery_data.py` 可能会抓取失败或者解析报错。排查思路：

1. 看 Actions 运行日志里 `[ERROR]` 后面打印的原始响应片段，判断是"完全请求不通"还是
   "请求通了但字段结构变了"
2. 如果是字段结构变了：把 GitHub Actions 日志里报错附近的原始 JSON 片段贴给我，我可以帮你
   照着新结构调整 `fetch_ssq()` / `fetch_dlt()` 里的解析代码
3. 抓取失败时脚本会保留上一次成功的旧数据文件不被清空，页面不会因此变白屏，只是数据会
   停留在最后一次成功抓取的时间点

---

## 本地预览

不依赖 GitHub Pages，也可以在本地直接看效果：

```bash
cd lottery-ledger
python3 -m http.server 8000
# 浏览器打开 http://localhost:8000
```

（如果直接用浏览器双击打开 `index.html`，会因为 `file://` 协议无法读取 `data/` 目录下的 JSON，
自动降级显示示例数据 —— 这是正常的，用上面的本地服务器方式或部署到 GitHub Pages 后就没有这个问题。）
