NOX 夜间独立研究/QA 整合候选（2026-10-18）

重要：本包不是已经验收的完整 NOX/NEX 桌面版，也不是安装器！
本轮工作环境没有上一轮声称存在的 NOX_Integrated_Nightly_RC1.zip 或 NOX 0.15 图形版源码，
所以无法安全合并或证明 Stage 1 快速聊天、Windows GUI、远控、直接向 ChatGPT 发消息。
本包只包含已实际获取的 NOX 0.9.2 研究核心，以及从 0.20.1 修复包中取得的 QA 验证器，
并加上夜间的定点可靠性增强和跨组件离线测试。

明天统一验收（不触碰现有安装版）：
  1. 解压 ZIP 到一个新目录，不要覆盖旧 NOX/NEX/Corvi。
  2. 双击 run.cmd。它先校验全部包内文件，再运行单元测试；若依赖齐全，
     用官方 Playwright MCP 在隔离 Chrome 里依次搜索并打开 Python 标准库
     statistics、pathlib、itertools 文档。任意一项失败即停止，不会重复点击。
  3. 结果在 reports/日期时间/REPORT_打开我.md 和 report.json。
     同目录还会生成不含用户路径的 handoff_summary.txt/json（仅本地保存，不自动发送）。

需要本机已有：Windows 10/11、Python 3、Node.js/npx、Ollama，且本地已有
qwen3.5:4b-q4_K_M。首次启动官方 Playwright MCP 时 npx 可能联网获取固定版本。
不安装 Python 第三方库，不自动下载 Ollama 模型，不修改用户的安装版。
仅检查离线逻辑可双击 offline_check.cmd。

夜间改动：
- 明确模块目标 + 唯一观察到的搜索框时，使用模块名精确检索，避免随机模型扩展搜索词。
- 只点击观察到的、匹配模块顶层主题的文档结果，排除 pathlib.Path 等同名成员。
- 点击后最多做三次只读 URL/标题/章节观察，容忍短暂加载延迟；绝不二次点击。
- QA 独立核对最终 Python 官方文档 URL、标题/章节、工具操作记录。
- 失败报告添加脱敏阶段代码，不要求用户从日志提取私人路径。
- QA 子进程输出写临时文件，仅读取末尾有限字节，避免大输出撑爆内存。
- 安装包清单 SHA256 校验，报告源代码目录的完整哈希。
- 自动生成只包含白名单字段的脱敏交接摘要，供以后连接消息桥使用。
- Windows 关闭隔离 Playwright MCP 时只清理本次启动的 cmd/npx/Chrome 子进程树。

限制：
- 仅 Linux 隔离环境完成离线测试，没有 Windows Playwright 真实三场景成功证据。
- 本包不会主动向 ChatGPT 发送消息，也不会自动修复 Windows 本机代码。
- pathlib 之前真实失败的具体日志未提供，尚不能证明根因已解决。
- 保留原 NOX 稳定版，不授权整机自动修改，不改 GitHub Release。

只在实际 Windows 三场景通过后，才可把此候选升级为下一阶段整合基础。

重要发现（2026-10-18 GitHub API 只读核验）：
  qa-0.9.2-r1 的 NOX-QA-source.zip 实际 SHA256 为
  97dd0aab141639bf1559b8523e70873d8a2ec282fc7d7d1ed8c5ca399df9cb4d
  它与 qa-0.9.1-r1 的源码附件完全相同。
  而之前在本对话生成的 0.20.1 新源码 ZIP 的 SHA256 为
  8012276d07388a2ac155e3432f318a7c89c65f08cb6ffcf4d4bacf83f2a88d90。
  因此上一次公网“SHA256_MATCH”仅证明匹配了旧包的预期值，
  不能证明 0.20.1 的新检索逻辑已实际进入公网测试。
  此问题已记录，但不会半夜修改 GitHub 或要求用户再次上传。
