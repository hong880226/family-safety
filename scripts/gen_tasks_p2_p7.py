"""Generate P2-P7 task documents."""
from pathlib import Path

DOCS = Path("E:/codeRepo/familysafety/docs")
DOCS.mkdir(parents=True, exist_ok=True)


P2 = """# FamilySafety 任务计划 - P2 LLM 答题

第 3 周，10 个任务。

## T201 LLM 客户端基类
- 范围：app/llm/client.py 基础 chat() 方法
- 验收：能成功调用 DeepSeek / Ollama
- 依赖：T102

## T202 本地题库（兜底）
- 范围：app/llm/fallback_bank.py
- 验收：5 个学科各 20+ 道题，LLM 故障时仍能出题
- 依赖：无

## T203 出题 Prompt 模板
- 范围：app/llm/prompts.py
- 验收：人工 review 10 次生成题目质量
- 依赖：无

## T204 generate_questions 服务
- 范围：app/llm/client.py 中 generate_questions()
- 验收：4 年级数学出 3 道题平均 < 10s
- 依赖：T201, T202, T203

## T205 judge_answers 服务
- 范围：app/llm/client.py 中 judge_answers()
- 验收：10 次人工评分准确率 > 95%
- 依赖：T204

## T206 答题会话 Schema
- 范围：QuizQuestion / QuizStartRequest / QuizSubmitRequest
- 验收：FastAPI 文档正确
- 依赖：T105

## T207 开始答题 API
- 范围：POST /api/v1/quiz/start
- 验收：E2E 测试可成功启动答题会话
- 依赖：T206, T204

## T208 提交答题 API
- 范围：POST /api/v1/quiz/submit
- 验收：80 分兑换 16 分钟（按规则）
- 依赖：T207, T205

## T209 答题会话状态机
- 范围：pending → in_progress → completed / expired
- 验收：超时会话不能继续作答
- 依赖：T208

## T210 答题缓存层（Redis）
- 范围：高频题目缓存、LLM 调用结果缓存
- 验收：连续 10 次请求只调 1 次 LLM
- 依赖：T207

P2 完成标志：手动跑一遍答题流程，LLM 题目 + 判分可用，故障时本地题库兜底。
"""


P3 = """# FamilySafety 任务计划 - P3 Windows 骨架

第 4 周，15 个任务。

## T301 .NET 解决方案
- 范围：FamilySafety.sln + 6 个项目骨架
- 验收：dotnet build 成功，无 warning
- 依赖：T001

## T302 Common 项目
- 范围：FamilySafety.Common/ 包含 Config / Logging / Models / Api / Native
- 验收：Service / Monitor 能引用
- 依赖：T301

## T303 全局 Directory.Build.props
- 范围：统一 LangVersion、Nullable、WarningsAsErrors
- 验收：dotnet build 无 warning
- 依赖：T301

## T304 Serilog 配置
- 范围：结构化日志，输出文件 + 控制台
- 验收：日志按天滚动
- 依赖：T302

## T305 Windows Service 项目
- 范围：FamilySafety.Service/ 项目骨架
- 验收：sc query FamilySafety 返回 RUNNING
- 依赖：T302

## T306 Service 启动逻辑
- 范围：OnStart 中启动 Guardian / Monitor / Tray
- 验收：服务启动后看到 3 个子进程
- 依赖：T305

## T307 Service 恢复策略
- 范围：sc.exe failure 配置（1 分钟内重启，最多 3 次）
- 验收：手动 kill 服务后 1 分钟内自动重启
- 依赖：T305

## T308 进程监控器（ProcessSupervisor）
- 范围：FamilySafety.Common 中实现
- 验收：杀 Monitor 后 5 秒内自动重启
- 依赖：T302

## T309 设备信息采集
- 范围：用户名、机器型号、操作系统版本、UUID
- 验收：DeviceInfo.Get() 在 Win10/11 正确
- 依赖：T302

## T310 后端 API 客户端
- 范围：FamilySafety.Common/Api/BackendClient.cs
- 验收：与 T107/T108/T110/T207/T208 对齐
- 依赖：T302

## T311 Monitor 项目骨架
- 范围：FamilySafety.Monitor/ 控制台项目
- 验收：dotnet run 启动成功
- 依赖：T302

## T312 前台窗口查询
- 范围：调用 Win32 API 获取前台进程
- 验收：在游戏窗口上能识别 steam.exe
- 依赖：T309

## T313 使用时长累加器
- 范围：UsageTracker.cs
- 验收：1 小时实测数据准确
- 依赖：T312, T310

## T314 策略引擎（PolicyEngine）
- 范围：根据本地时长 + 后端规则判断触发状态
- 验收：单测覆盖 10+ 场景
- 依赖：T313

## T315 Tray 项目骨架
- 范围：FamilySafety.Tray/ WPF 项目
- 验收：托盘图标 + 退出菜单（需家长密码）
- 依赖：T302

P3 完成标志：Windows 客户端 4 个项目骨架齐全，Service 启动后子进程全部拉起，Monitor 能识别前台窗口。
"""


P4 = """# FamilySafety 任务计划 - P4 守护 + UI

第 5 周，18 个任务。本周是项目最关键的阶段。

## T401 C++/CLI 项目初始化
- 范围：FamilySafety.Hooks.vcxproj
- 验收：能编译为 DLL
- 依赖：T301

## T402 键盘钩子基类（C++）
- 范围：LowLevelKeyboardProc
- 验收：测试程序能拦截 F1
- 依赖：T401

## T403 答题模式钩子策略
- 范围：Quiz 激活时禁用 Win/Alt+F4/Ctrl+Esc/Alt+Tab/F11
- 验收：手动测试有效
- 依赖：T402

## T404 C# Hook 封装
- 范围：FamilySafety.Monitor/Native/KeyboardHook.cs
- 验收：C# 能订阅按键事件
- 依赖：T403

## T405 Quiz 项目骨架（WPF）
- 范围：FamilySafety.Quiz/ WPF 项目
- 验收：空白窗口能启动
- 依赖：T302

## T406 Quiz 全屏窗口
- 范围：无边框、置顶、覆盖任务栏
- 验收：窗口无法被最小化
- 依赖：T405

## T407 Quiz ViewModel 基础
- 范围：MVVM 框架、ViewModelBase、RelayCommand
- 验收：UI 与逻辑解耦
- 依赖：T405

## T408 Quiz 视图：欢迎页
- 范围：显示「电脑超时啦，答对题可获得奖励」+ 开始按钮
- 验收：深色简约风，设计师 review 通过
- 依赖：T406, T407

## T409 Quiz 视图：答题页
- 范围：题干 + 4 个选项 + 提交按钮 + 倒计时
- 验收：能完整答完一题
- 依赖：T408

## T410 Quiz 视图：结果页
- 范围：得分 + 奖励时长 + 解析
- 验收：得分动画流畅
- 依赖：T409

## T411 Quiz 与后端通信
- 范围：启动调 /quiz/start，提交调 /quiz/submit
- 验收：后端日志可见调用
- 依赖：T410, T310

## T412 Guardian 项目骨架
- 范围：FamilySafety.Guardian/ 控制台项目
- 验收：dotnet run 启动成功
- 依赖：T302

## T413 Guardian 监控 + 拉起
- 范围：监控 Monitor / Quiz / Tray 进程
- 验收：压力测试 10 次杀 Monitor 都能恢复
- 依赖：T412, T308

## T414 Guardian 反 taskkill
- 范围：检测自己被 taskkill 时反制
- 验收：taskkill /f 杀 Guardian 后 3 秒内恢复
- 依赖：T413

## T415 任务管理器拦截
- 范围：Hook taskmgr.exe，屏蔽 End Task 菜单
- 验收：选中自家进程时右键无 End Task
- 依赖：T401, T404

## T416 家长密码模块
- 范围：PBKDF2 哈希、首次设置、修改密码
- 验收：错误密码 5 次锁定 5 分钟
- 依赖：T302

## T417 配置文件加密存储
- 范围：敏感字段（api_key, password_hash）加密
- 验收：明文查看 config.json 看不到敏感字段
- 依赖：T302

## T418 E2E 测试：超时答题流程
- 范围：手动 + 自动化测试
- 验收：完整流程通过
- 依赖：T411, T414

P4 完成标志：完整超时答题 E2E 跑通，含 Hook 强制；杀进程测试通过。
"""


P5 = """# FamilySafety 任务计划 - P5 家长端

第 6 周，8 个任务。

## T501 Dashboard 基础框架
- 范围：Jinja2 + 简单 HTML + 深色简约风
- 验收：访问 /dashboard 看到导航
- 依赖：T105

## T502 家长登录
- 范围：JWT 登录、家长账号
- 验收：错误密码拒绝
- 依赖：T501

## T503 Dashboard 概览页
- 范围：今日 / 本周时长、Top 应用、最近答题
- 验收：Chart.js 数据准确
- 依赖：T502

## T504 Dashboard 详细数据页
- 范围：按天 / 按应用聚合查询
- 验收：查询性能 OK
- 依赖：T503

## T505 成员管理 CRUD
- 范围：增删改查成员
- 验收：能添加孩子并设置 grade
- 依赖：T502

## T506 规则配置页
- 范围：可视化编辑规则、匹配键预览
- 验收：配置后 Agent 心跳能拿到新规则
- 依赖：T505

## T507 设备管理页
- 范围：查看在线设备、撤销 API Key
- 验收：撤销后 Agent 鉴权失败
- 依赖：T502

## T508 LLM 配置页
- 范围：家长可配置 LLM base_url / api_key / model
- 验收：配置后立即生效
- 依赖：T502

P5 完成标志：家长可登录看板，能配置成员、规则、设备、LLM。
"""


P6 = """# FamilySafety 任务计划 - P6 打包发布

第 7 周，6 个任务。

## T601 Inno Setup 脚本
- 范围：installer/installer.iss
- 验收：能编译出 Setup.exe
- 依赖：T301

## T602 安装时注册 Windows Service
- 范围：安装时自动 sc create
- 验收：重启电脑后服务自动启动
- 依赖：T601

## T603 首次启动家长密码设置向导
- 范围：首次启动检测无密码时弹出设置页
- 验收：未设置时强制设置
- 依赖：T416

## T604 自动注册到后端
- 范围：首次启动自动调 /agent/register
- 验收：后端能看到设备
- 依赖：T310, T603

## T605 卸载脚本
- 范围：卸载时停止服务、清理文件
- 验收：控制面板卸载干净
- 依赖：T601

## T606 部署文档
- 范围：docs/ops.md
- 验收：陌生人按文档能完成 Debian + 客户端部署
- 依赖：T601

P6 完成标志：双击 Setup.exe 完成全流程安装，自动注册到后端。
"""


P7 = """# FamilySafety 任务计划 - P7 1.0 发布

第 8 周，4 个任务。

## T701 全功能 E2E 测试
- 范围：10 个核心场景自动化测试
- 验收：全部通过
- 依赖：P1-P6 全部完成

## T702 性能与压力测试
- 范围：10 台设备同时上报
- 验收：P99 < 500ms
- 依赖：T701

## T703 安全审计
- 范围：OWASP Top 10 自查
- 验收：无 High 级别漏洞
- 依赖：T701

## T704 v1.0 发布
- 范围：Release tag、Docker image、下载页
- 验收：5 个非开发人员成功部署
- 依赖：T701, T702, T703

P7 完成标志：v1.0 正式发布。
"""


files = {
    "tasks-p2.md": P2,
    "tasks-p3.md": P3,
    "tasks-p4.md": P4,
    "tasks-p5.md": P5,
    "tasks-p6.md": P6,
    "tasks-p7.md": P7,
}

for name, content in files.items():
    target = DOCS / name
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {name}: {len(content)} bytes")

print(f"\nAll task documents:")
for p in sorted(DOCS.glob("tasks-*.md")):
    print(f"  {p.name} ({p.stat().st_size} bytes)")