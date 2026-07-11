# FamilySafety 任务计划 - P3 Windows 骨架

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
