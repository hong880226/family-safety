# FamilySafety 用户指南

本文档面向**已经部署完成** FamilySafety 的家长，介绍日常使用流程。

> **未部署？** 请先看 [`../deploy/README.md`](../deploy/README.md) 完成服务端部署，
> 然后看 [`agent-windows/README.md`](../agent-windows/README.md) 完成 Windows 客户端打包。

---

## 1. 首次登录

部署后端 + 在孩子电脑上安装客户端后，服务端会自动创建一个新家庭并生成家长账号。
客户端安装向导的最后一屏会显示：

```
家长用户名: parent_<family_id>
初始密码:   <随机 12 字符>
family_setup_token: FAM-...   ← 加入同一家庭时使用
```

把这三个值记下来（截图保存），然后：

1. 浏览器打开 `https://<你的域名>/web/login`
2. 输入用户名 + 密码登录
3. **立刻修改密码**：左侧导航栏 → 修改密码（旧密码 + 新密码 ≥ 8 字符）

> 忘记初始密码？重新运行服务端不会改密码。请登录到服务器，
> 执行数据库重置脚本或联系管理员。

---

## 2. 添加孩子

登录后 → **成员** 页面 → 填写：

| 字段 | 说明 |
|------|------|
| 姓名 | 显示在周报里，建议用真名 |
| 年级 | 1–12，控制出题难度 |
| Windows 用户名 | 孩子在这台电脑上的登录账号。**留空则匹配所有用户名**（不推荐） |

每个孩子匹配一台电脑用 `(姓名 + 电脑型号 + Windows 用户名)` 三元组。同一台电脑多个孩子切换登录，
系统会自动识别。

---

## 3. 添加设备

设备在客户端**首次启动**时自动注册。如果孩子换电脑：

1. 在新电脑上安装客户端
2. 启动时填入 `family_setup_token`（首次创建家庭时拿到的）
3. 完成后会得到 `device_id` 和 `api_key`，**自动**出现在 web 看板的「设备」页

要**撤销**某台设备：web 看板 → 设备 → 删除。客户端会停止上报，下次启动时再次注册会被拒绝。

---

## 4. 设置每日时长与作息

web 看板 → **规则** 页面：

- **每日上限**（分钟）：超出后强制答题
- **睡前时段**：开始–结束时段内强制弹锁屏
- **监控应用**：留空监控所有应用；填具体名（chrome.exe 等）只监控这些

每条规则绑定到某个孩子 + 某个电脑型号 / Windows 用户名。

---

## 5. 配置答题（兑换时长）

web 看板 → **答题配置**：

- **总题数**：1–20
- **难度**：1（最简单）– 5（最难）
- **学科**：逗号分隔，如 `math,chinese,english`
- **分配模式**：
  - `auto`：系统根据孩子弱项自动分配
  - `weak_first`：先抽弱项学科
  - `balanced`：平均分配

孩子完成答题后，每答对 1 题兑换 `每日上限 × reward_ratio` 分钟。`reward_ratio` 在「规则」页可调。

---

## 6. 内容过滤

web 看板 → **内容规则**：

- **匹配类型**：
  - `process_name`：匹配应用进程名（如 `chrome.exe`）
  - `window_title`：匹配窗口标题关键词
- **pattern**：正则表达式，限 200 字符以防 ReDoS
- **类别**：毒视频 / 游戏 / 短视频 / 学习 / 自定义
- **action**：
  - `monitor`：仅记录
  - `block`：阻断访问
  - `flag_for_llm`：送 LLM 二次判定

设置后所有该家庭的设备立即生效。

---

## 7. 毒视频告警

LLM 二次判定命中后会在 web 看板 → **毒视频告警** 出现。

- 红点：未确认
- 灰点：已确认

请按情况点击「确认」。如果判断错误，可以把规则标记为正常。

---

## 8. 周报

web 看板 → **周报**：每周一早上 8 点（默认）自动生成。

要在邮箱收到周报：

1. web 看板 → **推送设置**
2. 填 SMTP 信息（推荐 Gmail SMTP / QQ 邮箱 SMTP / 自建 Postfix）
3. 填收件邮箱
4. 勾选「每周邮件推送」
5. 测试发送：保存后会自动发一封测试邮件

### 推荐的 SMTP 设置

| 服务 | host | port | 加密 |
|------|------|------|------|
| Gmail | smtp.gmail.com | 587 | STARTTLS |
| QQ 邮箱 | smtp.qq.com | 587 | STARTTLS |
| Outlook | smtp.office365.com | 587 | STARTTLS |
| 自建 Postfix | your.mail.host | 25 / 587 | STARTTLS（推荐）|

> 注意：QQ / 163 / Gmail 等多数云邮箱需要**应用专用密码**而非登录密码。
> 密码以 Fernet 加密后存库，不会以明文落盘。

---

## 9. 修改密码 / 退出

- **修改密码**：左侧导航栏 → 修改密码
- **退出登录**：左下角 → 退出

---

## 10. 卸载客户端

**Windows 控制面板 → 程序和功能 → FamilySafety Agent → 卸载**。

PowerShell 也可：
```powershell
& "C:\Program Files\FamilySafety\Uninstall-FamilySafety.ps1"
```

卸载脚本会：
1. 停止所有 FamilySafety 进程
2. 撤销服务端 API key（服务端设备列表中标记 `revoked=True`）
3. 删除 `C:\Program Files\FamilySafety\` 和注册表项
4. 保留使用记录备份到桌面（如需要）

---

## 11. 备份 / 还原

数据全在数据库里。备份 = 备份数据库。

```bash
# 备份
docker exec familysafety-db pg_dump -U familysafety familysafety > backup_$(date +%F).sql

# 还原（先停服务）
docker compose stop backend
cat backup_2026-07-11.sql | docker exec -i familysafety-db psql -U familysafety familysafety
docker compose start backend
```

备份包含 SMTP 密码（Fernet 加密），但**不会**包含 JWT_SECRET。
换机器还原时务必保留同一个 `JWT_SECRET` + `FERNET_KEY`，否则家长登录态失效、SMTP 密码无法解密。

---

## 12. 多家庭支持

服务端默认是**单家庭**模式（所有设备共享一个家长账号）。要支持多家庭：

1. 每个家庭在第一台设备注册时拿到自己的 `family_setup_token`
2. 后续设备用对应 token 加入

如果两个家庭注册时间不同，第一个家长不会看到第二个家庭的数据（所有查询按 `family_id` 过滤）。

---

## 下一步

- 排错：[`troubleshooting.md`](./troubleshooting.md)
- 架构：[`architecture.md`](./architecture.md)