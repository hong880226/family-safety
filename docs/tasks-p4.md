# FamilySafety 任务计划 - P4 守护 + UI

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
