# scripts/

历史 code-generation / patch 脚本。**不再用于日常开发**，保留以备复盘 / 重建某个 phase。

每个 `gen_pN_*.py` 是一次性脚本，生成对应 phase 的代码（routes、templates、API 等）。
`patch_*.py` 是就地修改脚本。

## 重建流程

如果仓库被破坏，可以按编号顺序重跑：

```bash
python scripts/gen_backend_skeleton.py
python scripts/gen_p2_module1.py
python scripts/gen_p2_services.py
python scripts/gen_p2_quiz_api.py
python scripts/gen_p2_notification.py
python scripts/gen_p2_content.py
python scripts/gen_p3_common.py
python scripts/gen_p3_agents.py
python scripts/gen_p4_hardening.py
python scripts/gen_p5_routes.py
python scripts/gen_p5_templates.py
python scripts/gen_docker.py
python scripts/gen_tasks.py
python scripts/gen_tasks_p2_p7.py
```

然后按需要：

```bash
python scripts/patch_architecture.py
python scripts/patch_arch_v2.py
python scripts/patch_tasks_p2_p5.py
python scripts/patch_v2.py
python scripts/fix_p1.py
python scripts/rewrite_classifier.py
python scripts/fix_escapes.py
```

⚠️ **警告**：脚本可能与当前代码状态不同步（已被手工修改）。重跑前务必：
1. 备份当前代码
2. 与最新代码 review 脚本输出
3. 不要在生产环境跑

## 一次性脚本（生成后即可删除）

如果确认这些脚本已完成历史使命，可以安全删除整个 `scripts/` 目录。
所有功能都已经在 `backend/app/` 中实现。