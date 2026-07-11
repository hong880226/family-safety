# FamilySafety 任务计划 - P2 LLM 答题

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

P2 完成标志（基础）：手动跑一遍答题流程，LLM 题目 + 判分可用，故障时本地题库兜底。


## T211 QuizConfig 模型与 API
- 范围：QuizConfig 表、CRUD API、关联 Rule
- 验收：能配置学科、难度、分布；更新后立即生效
- 依赖：T104, T108

## T212 出题分布计算服务
- 范围：app/services/distribution.py
- 验收：支持 manual / auto / weakness_first 三种模式
- 依赖：T211, T214

## T213 多学科批量出题
- 范围：generate_questions 支持批量多学科
- 验收：5 道题跨 3 学科，生成 < 15s
- 依赖：T204, T212

## T214 SubjectMastery 模型与计算
- 范围：SubjectMastery 表、update_mastery 服务
- 验收：30 天数据准确率正确，弱项标记正确
- 依赖：T104

## T215 Quiz Start 集成 QuizConfig
- 范围：/quiz/start 改用 QuizConfig 生成题目
- 验收：响应中含 config_used 字段
- 依赖：T213, T214

## T216 内容分类服务（Agent 端）
- 范围：app/services/classifier.py（后端），C# 端 L1+L2 实现
- 验收：能识别游戏/浏览器/短视频
- 依赖：T113

## T217 LLM 毒视频判定
- 范围：app/services/toxic_judge.py
- 验收：100 个样本准确率 > 85%
- 依赖：T205, T113

## T218 周报数据汇总服务
- 范围：app/services/weekly_report.py
- 验收：周报 summary 字段完整正确
- 依赖：T110, T214

## T219 周报 LLM 内容生成
- 范围：基于 summary 生成教育建议正文
- 验收：人工 review 5 份周报，4 份以上可用
- 依赖：T218, T205

## T220 邮件推送
- 范围：SMTP 客户端 + 模板渲染
- 验收：测试邮件能收到
- 依赖：T115, T219

## T221 定时任务（APScheduler）
- 范围：每周日晚 8 点生成周报
- 验收：手动调整时间能触发
- 依赖：T219, T220

P2 完成标志：内容分类可用；LLM 毒视频判定准确；周报生成 + 邮件推送全流程跑通。

