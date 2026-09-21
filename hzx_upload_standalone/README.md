# 华之星证书上传（独立版）

独立 Python 程序，双击或命令行即可运行，
不依赖外部自动化运行环境。

## 与原 `hzx_certificate_upload.py` 的区别
- 去掉硬编码的个人电脑结果路径，输出目录可配置（默认 `results/`）。
- 去掉对外部自动化 Python 环境的依赖，使用本机 Python 3.12 运行。
- 分层：config / logger / crypto_cred(凭证加密) / state(断点重跑) / io_read(输入解析) / client(API) / level1(一级占位) / level2(二级)。
- 修正原代码对「商品名 / 上传反馈」列的硬依赖（真实明细表无这两列）；证书类别由文件名前缀(WEEE-/BAT-)推断。

## 目录结构
```
hzx_upload_standalone/
  config.py        配置（URL/路径/账号，可写 config.json）
  logger.py        日志（控制台+文件）
  crypto_cred.py   账号密码本地加密(Fernet)
  state.py         断点重跑状态(state.json)
  io_read.py       输入解析（注册表/明细表/截图/证书）
  client.py        华之星后台 API
  ratelimit.py     防封护栏（间隔抖动/速率帽/断路器/时间窗）
  level1.py        一级代办（截图上传，接口占位）
  level2.py        二级代办（证书上传，可用）
  main.py          命令行入口
  gui.py           GUI 外壳（tkinter，复用 run_pipeline）
  启动.bat         双击运行命令行版（Windows）
  启动GUI.bat      双击运行图形界面版（Windows）
```

## 运行
- 图形界面（推荐）：双击 `启动GUI.bat`，选任务包目录 → 勾选层级/模拟 → 开始运行，日志实时显示。
- 命令行：双击 `启动.bat`（默认把本目录当作任务包，`--dry-run` 关闭时为真实上传）。
- 或命令行：
  ```
  python main.py --task-package "任务包目录" --dry-run
  python main.py --task-package "任务包目录" --level2        # 真实上传
  python main.py --task-package "任务包目录" --level1 --level2 --date 2026/8/25
  ```
- 首次真实上传需账号密码：用 `--username/--password`，或 `--save-cred` 加密保存。

## 防封 / 限流配置（config.json）
登录每批次只发生 1 次（会话 token 全程复用），待办列表整批只拉 1 次，不存在「每条数据都登录」。
为降低被限流/封域名风险，已内置以下保守默认，可在 `config.json` 覆盖：

基础参数：
- `request_interval` (默认 1.0)：两次上传之间的基础间隔秒数。
- `max_retries` (默认 3)：单次上传失败的网络重试次数。
- `retry_backoff` (默认 2.0)：重试退避基数(秒)，按指数 `2^(n-1)` 增长。

防封强化层（默认保守，策略逻辑在 `ratelimit.py`）：
- `request_jitter` (默认 0.5)：间隔随机抖动比例(0~1)。实际等待 = `interval + interval*jitter*rand()`，使节奏更像人工、避免固定周期被识别为脚本。
- `circuit_breaker` (默认 3)：连续失败达到此数，**立即中止整批**（断点重跑可续），避免在被封/限流时硬扛放大风险。
- `max_per_hour` (默认 60)：每小时最多上传数(0=不限)，尊重未知的系统硬限流。
- `business_hours` (默认 [9,18])：业务时间窗 `[起, 止)`；窗口外运行会休眠至下一个窗口开始（等待超 `max_schedule_wait` 则中止）。设 `null` 关闭。
- `probe_first` (默认 true)：开跑前先验证会话健康（拉一次待办列表），若已限流/封禁则直接中止，不触碰上传。
- `max_schedule_wait` (默认 7200)：非业务时间窗最多等待秒数，超出则中止。

自动防护：遇 `401` 自动重新登录后重试；遇 `429/5xx/超时/断连` 按退避重试；待办列表超 200 条自动翻页。
注意：代码层可把风险降到很低，但无法 100% 保证不被封——最终取决于平台是否允许自动化、所用账号是否核心、出口 IP 是否干净（非技术因素）。

## 当前状态 / 待办
- 二级代办：可用（API 已验证），支持 dry-run、断点重跑、防封强化层。
- 一级代办：接口已留，真实上传待确认「上传ID和截图」是否为 API（待确认清单#7）。
- GUI：已提供 tkinter 图形界面（`gui.py` + `启动GUI.bat`），复用同一套业务逻辑。
- 凭证加密、状态重跑、日志、防封护栏均已就绪。
- BAT 电池法样例缺失，batt 分支未用真实数据验证（逻辑已按前缀区分）。
