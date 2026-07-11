"""P5: Generate dashboard templates + routes + static assets."""
from pathlib import Path

BACKEND = Path("E:/codeRepo/familysafety/backend")
TEMPLATES = BACKEND / "app" / "web" / "templates"
STATIC = BACKEND / "app" / "web" / "static"


def write_file(rel: str, content: str, root: Path = BACKEND) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {target.relative_to(BACKEND)} ({len(content)} bytes)")


# === Init module ===
write_file("app/web/__init__.py", '"""Web dashboard (Jinja2 + HTMX)."""\n')
write_file("app/web/templates/__init__.py", "")
write_file("app/web/static/__init__.py", "")

# === Auth pages ===
write_file("app/web/templates/login.html", '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>登录 · FamilySafety</title>
  <link rel="stylesheet" href="/static/css/app.css" />
</head>
<body class="auth-page">
  <div class="auth-card">
    <div class="auth-logo">
      <div class="logo-mark"></div>
      <h1>FamilySafety</h1>
      <p class="auth-subtitle">家长控制中心</p>
    </div>
    <form method="post" action="/web/login" class="auth-form">
      <label class="field">
        <span>用户名</span>
        <input type="text" name="username" required autofocus />
      </label>
      <label class="field">
        <span>密码</span>
        <input type="password" name="password" required />
      </label>
      {% if error %}
      <div class="alert alert-error">{{ error }}</div>
      {% endif %}
      <button type="submit" class="btn btn-primary btn-block">登录</button>
    </form>
    <p class="auth-hint">首次安装后默认账号：家长用户名（创建家庭时设定）</p>
  </div>
</body>
</html>
''')

# === Layout ===
write_file("app/web/templates/_layout.html", '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{% block title %}FamilySafety{% endblock %}</title>
  <link rel="stylesheet" href="/static/css/app.css" />
  <script src="/static/js/htmx.min.js" defer></script>
</head>
<body class="app-body">
  <aside class="sidebar">
    <div class="brand">
      <div class="logo-mark small"></div>
      <span>FamilySafety</span>
    </div>
    <nav class="nav">
      <a href="/web/dashboard" class="nav-item {% if active=='dashboard' %}active{% endif %}">概览</a>
      <a href="/web/members" class="nav-item {% if active=='members' %}active{% endif %}">成员</a>
      <a href="/web/devices" class="nav-item {% if active=='devices' %}active{% endif %}">设备</a>
      <a href="/web/rules" class="nav-item {% if active=='rules' %}active{% endif %}">规则</a>
      <a href="/web/quiz-config" class="nav-item {% if active=='quiz' %}active{% endif %}">答题配置</a>
      <a href="/web/mastery" class="nav-item {% if active=='mastery' %}active{% endif %}">弱项分析</a>
      <a href="/web/content-rules" class="nav-item {% if active=='content' %}active{% endif %}">内容规则</a>
      <a href="/web/toxic-alerts" class="nav-item {% if active=='toxic' %}active{% endif %}">毒视频告警</a>
      <a href="/web/weekly-reports" class="nav-item {% if active=='reports' %}active{% endif %}">周报</a>
      <a href="/web/settings" class="nav-item {% if active=='settings' %}active{% endif %}">推送设置</a>
    </nav>
    <div class="sidebar-footer">
      <span class="muted">v{{ version }}</span>
      <a href="/web/logout" class="muted">退出</a>
    </div>
  </aside>

  <main class="main">
    <header class="page-header">
      <h1>{% block heading %}{% endblock %}</h1>
      <div class="page-actions">{% block actions %}{% endblock %}</div>
    </header>

    <section class="page-body">
      {% block content %}{% endblock %}
    </section>
  </main>
</body>
</html>
''')

# === Dashboard ===
write_file("app/web/templates/dashboard.html", '''{% extends "_layout.html" %}
{% block heading %}概览{% endblock %}
{% set active = 'dashboard' %}
{% block content %}
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">今日已用</div>
    <div class="kpi-value">{{ summary.today_minutes }} <span class="kpi-unit">分钟</span></div>
    <div class="kpi-bar"><div class="kpi-bar-fill" style="width: {{ summary.used_vs_limit_percent }}%"></div></div>
    <div class="kpi-sub muted">{{ summary.used_vs_limit_percent|round(0) }}% / {{ summary.daily_limit }} 分钟</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">本周累计</div>
    <div class="kpi-value">{{ summary.week_minutes }} <span class="kpi-unit">分钟</span></div>
    <div class="kpi-sub muted">较上周 {{ summary.week_delta|default(0) }}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">本周超时</div>
    <div class="kpi-value">{{ summary.overtime_count_this_week }}</div>
    <div class="kpi-sub muted">次</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">最近答题</div>
    <div class="kpi-value muted">{{ summary.last_quiz_at or '—' }}</div>
  </div>
</div>

<div class="grid-2">
  <div class="panel">
    <h3 class="panel-title">今日 Top 应用</h3>
    <table class="table">
      <thead><tr><th>应用</th><th class="right">分钟</th><th></th></tr></thead>
      <tbody>
        {% for app in summary.top_apps %}
        <tr>
          <td>{{ app.name }}</td>
          <td class="right">{{ app.minutes }}</td>
          <td class="bar-cell"><div class="bar" style="width: {{ app.percent }}%"></div></td>
        </tr>
        {% else %}
        <tr><td colspan="3" class="muted center">今天还没有数据</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <div class="panel">
    <h3 class="panel-title">内容分类</h3>
    <div class="category-bars">
      {% for cat, mins in summary.category_breakdown.items() %}
      <div class="cat-row">
        <span class="cat-label">{{ cat }}</span>
        <div class="cat-bar"><div class="cat-bar-fill" style="width: {{ summary.category_pct[cat] }}%"></div></div>
        <span class="cat-val">{{ mins }} 分钟</span>
      </div>
      {% else %}
      <p class="muted">暂无数据</p>
      {% endfor %}
    </div>
  </div>
</div>

<div class="panel">
  <h3 class="panel-title">本周答题表现</h3>
  {% if summary.quiz_summary %}
    <p>共 {{ summary.quiz_summary.count }} 次答题，{{ summary.quiz_summary.questions }} 道题，平均正确率 {{ summary.quiz_summary.accuracy }}%</p>
    <p class="muted">继续努力！</p>
  {% else %}
    <p class="muted">本周还没有答题记录</p>
  {% endif %}
</div>
{% endblock %}
''')

# === Members ===
write_file("app/web/templates/members.html", '''{% extends "_layout.html" %}
{% block heading %}成员{% endblock %}
{% set active = 'members' %}
{% block content %}
<div class="grid-2">
  <div class="panel">
    <h3 class="panel-title">现有成员</h3>
    <table class="table">
      <thead><tr><th>姓名</th><th>角色</th><th>年级</th><th>Windows 用户名</th><th></th></tr></thead>
      <tbody>
        {% for m in members %}
        <tr>
          <td>{{ m.name }}</td>
          <td>{% if m.role=='parent' %}家长{% else %}孩子{% endif %}</td>
          <td>{{ m.grade or '—' }}</td>
          <td><code>{{ m.windows_username or '—' }}</code></td>
          <td><a href="/web/members/{{ m.id }}/edit" class="btn btn-sm">编辑</a></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <div class="panel">
    <h3 class="panel-title">添加孩子</h3>
    <form method="post" action="/web/members" class="form">
      <label class="field"><span>姓名</span><input name="name" required /></label>
      <label class="field"><span>年级</span><input type="number" name="grade" min="1" max="12" value="4" /></label>
      <label class="field"><span>Windows 用户名</span><input name="windows_username" placeholder="kid01" /></label>
      <button type="submit" class="btn btn-primary">添加</button>
    </form>
  </div>
</div>
{% endblock %}
''')

# === Devices ===
write_file("app/web/templates/devices.html", '''{% extends "_layout.html" %}
{% block heading %}设备{% endblock %}
{% set active = 'devices' %}
{% block content %}
<div class="panel">
  <table class="table">
    <thead><tr><th>名称</th><th>成员</th><th>型号</th><th>最后在线</th><th>状态</th><th></th></tr></thead>
    <tbody>
      {% for d in devices %}
      <tr>
        <td>{{ d.name }}</td>
        <td>{{ d.member_name or '—' }}</td>
        <td><code>{{ d.computer_model or '—' }}</code></td>
        <td>{{ d.last_seen or '—' }}</td>
        <td>{% if d.online %}<span class="badge badge-ok">在线</span>{% else %}<span class="badge badge-muted">离线</span>{% endif %}</td>
        <td><form method="post" action="/web/devices/{{ d.id }}/delete" onsubmit="return confirm('确定撤销此设备？')"><button class="btn btn-sm btn-danger">撤销</button></form></td>
      </tr>
      {% else %}
      <tr><td colspan="6" class="muted center">还没有设备，请先在孩子电脑上运行 FsWatchdog</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
''')

# === Rules ===
write_file("app/web/templates/rules.html", '''{% extends "_layout.html" %}
{% block heading %}规则{% endblock %}
{% set active = 'rules' %}
{% block content %}
<div class="panel">
  <table class="table">
    <thead><tr><th>成员</th><th>规则名</th><th>匹配</th><th>每日限额</th><th>每次答题</th><th>状态</th></tr></thead>
    <tbody>
      {% for r in rules %}
      <tr>
        <td>{{ r.member_name }}</td>
        <td>{{ r.name }}</td>
        <td><code>{{ r.match_key }}</code></td>
        <td>{{ r.daily_limit_minutes }} 分钟</td>
        <td>{{ r.questions_per_session }} 题</td>
        <td>{% if r.enabled %}<span class="badge badge-ok">启用</span>{% else %}<span class="badge badge-muted">停用</span>{% endif %}</td>
      </tr>
      {% else %}
      <tr><td colspan="6" class="muted center">暂无规则。设备首次注册时会自动创建默认规则。</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
''')

# === Quiz config ===
write_file("app/web/templates/quiz_config.html", '''{% extends "_layout.html" %}
{% block heading %}答题配置{% endblock %}
{% set active = 'quiz' %}
{% block content %}
<div class="grid-2">
  <div class="panel">
    <h3 class="panel-title">选择成员</h3>
    <form method="get" action="/web/quiz-config">
      <select name="member_id" onchange="this.form.submit()">
        <option value="">— 选择 —</option>
        {% for m in members %}
          <option value="{{ m.id }}" {% if member and member.id==m.id %}selected{% endif %}>{{ m.name }}</option>
        {% endfor %}
      </select>
    </form>
  </div>
  {% if member %}
  <div class="panel">
    <h3 class="panel-title">为 {{ member.name }} 配置</h3>
    <form method="post" action="/web/quiz-config" class="form">
      <input type="hidden" name="member_id" value="{{ member.id }}" />
      <label class="field">
        <span>每次答题数</span>
        <input type="number" name="total_questions" min="1" max="20" value="{{ cfg.total_questions }}" />
      </label>
      <label class="field">
        <span>难度等级 (1-5)</span>
        <input type="number" name="difficulty" min="1" max="5" value="{{ cfg.difficulty }}" />
      </label>
      <label class="field">
        <span>学科（逗号分隔）</span>
        <input name="subjects" value="{{ cfg.subjects|join(',') }}" />
      </label>
      <label class="field">
        <span>分布模式</span>
        <select name="distribution_mode">
          <option value="manual" {% if cfg.distribution_mode=='manual' %}selected{% endif %}>手动</option>
          <option value="auto" {% if cfg.distribution_mode=='auto' %}selected{% endif %}>自动平均</option>
          <option value="weakness_first" {% if cfg.distribution_mode=='weakness_first' %}selected{% endif %}>弱项优先</option>
        </select>
      </label>
      <button type="submit" class="btn btn-primary">保存</button>
    </form>
  </div>
  {% endif %}
</div>
{% endblock %}
''')

# === Mastery (弱项分析) ===
write_file("app/web/templates/mastery.html", '''{% extends "_layout.html" %}
{% block heading %}弱项分析{% endblock %}
{% set active = 'mastery' %}
{% block content %}
<div class="grid-2">
  <div class="panel">
    <h3 class="panel-title">{{ member.name }} 各科准确率</h3>
    {% if mastery %}
    <div class="radar-wrap">
      <table class="table">
        <thead><tr><th>学科</th><th>已答题数</th><th>正确率</th><th>是否弱项</th></tr></thead>
        <tbody>
          {% for subj, m in mastery.items() %}
          <tr>
            <td>{{ subj }}</td>
            <td>{{ m.total }}</td>
            <td>
              <div class="bar-mini"><div class="bar-mini-fill" style="width: {{ m.accuracy*100 }}%; background: {{ m.is_weak and 'var(--warn)' or 'var(--ok)' }}"></div></div>
              <span class="muted"> {{ (m.accuracy*100)|round(0) }}%</span>
            </td>
            <td>{% if m.is_weak %}<span class="badge badge-warn">弱项</span>{% else %}<span class="badge badge-ok">良好</span>{% endif %}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <p class="muted">还没有答题数据。让孩子多答题后再来看。</p>
    {% endif %}
  </div>

  {% if suggestions %}
  <div class="panel">
    <h3 class="panel-title">LLM 给出的建议</h3>
    {% for s in suggestions %}
    <div class="suggestion">
      <h4>{{ s.title }}</h4>
      <p>{{ s.content }}</p>
      <small class="muted">置信度: {{ (s.confidence*100)|round(0) }}%</small>
    </div>
    {% endfor %}
  </div>
  {% endif %}
</div>
{% endblock %}
''')

# === Content rules ===
write_file("app/web/templates/content_rules.html", '''{% extends "_layout.html" %}
{% block heading %}内容规则{% endblock %}
{% set active = 'content' %}
{% block content %}
<div class="grid-2">
  <div class="panel">
    <h3 class="panel-title">当前规则</h3>
    <table class="table">
      <thead><tr><th>类型</th><th>模式</th><th>分类</th><th>动作</th><th>启用</th><th></th></tr></thead>
      <tbody>
        {% for r in rules %}
        <tr>
          <td><span class="tag">{{ r.match_type }}</span></td>
          <td><code>{{ r.pattern[:40] }}{% if r.pattern|length > 40 %}...{% endif %}</code></td>
          <td>{{ r.category }}</td>
          <td>{% if r.action=='block' %}<span class="badge badge-warn">拦截</span>{% elif r.action=='flag_for_llm' %}<span class="badge badge-warn">送 LLM</span>{% elif r.action=='warn' %}<span class="badge badge-info">警告</span>{% else %}<span class="badge badge-muted">监控</span>{% endif %}</td>
          <td>{% if r.enabled %}✓{% else %}—{% endif %}</td>
          <td><a href="/web/content-rules/{{ r.id }}/edit" class="btn btn-sm">编辑</a></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <div class="panel">
    <h3 class="panel-title">添加规则</h3>
    <form method="post" action="/web/content-rules" class="form">
      <label class="field"><span>匹配类型</span>
        <select name="match_type">
          <option value="process">进程名</option>
          <option value="window_title">窗口标题</option>
          <option value="domain">域名</option>
          <option value="url">URL</option>
        </select>
      </label>
      <label class="field"><span>正则表达式</span><input name="pattern" placeholder="例如 (?i)steam\.exe$" required /></label>
      <label class="field"><span>分类</span>
        <select name="category">
          <option value="game_native">原生游戏</option>
          <option value="game_web">网页游戏</option>
          <option value="short_video">短视频</option>
          <option value="video_long">长视频</option>
          <option value="social">社交</option>
          <option value="study">学习</option>
          <option value="toxic_content">毒视频</option>
          <option value="unknown">未知</option>
        </select>
      </label>
      <label class="field"><span>动作</span>
        <select name="action">
          <option value="monitor">仅监控</option>
          <option value="warn">警告</option>
          <option value="block">拦截</option>
          <option value="flag_for_llm">送 LLM 二次判定</option>
        </select>
      </label>
      <button type="submit" class="btn btn-primary">添加</button>
    </form>
  </div>
</div>
{% endblock %}
''')

# === Toxic alerts ===
write_file("app/web/templates/toxic_alerts.html", '''{% extends "_layout.html" %}
{% block heading %}毒视频告警{% endblock %}
{% set active = 'toxic' %}
{% block content %}
<div class="panel">
  {% if alerts %}
  <table class="table">
    <thead><tr><th>时间</th><th>成员</th><th>应用</th><th>窗口标题</th><th>分类</th><th>置信度</th><th>原因</th><th>已通知</th><th></th></tr></thead>
    <tbody>
      {% for a in alerts %}
      <tr>
        <td>{{ a.created_at }}</td>
        <td>{{ a.member_name }}</td>
        <td>{{ a.app_name }}</td>
        <td>{{ a.window_title[:50] }}</td>
        <td><span class="badge badge-warn">{{ a.category }}</span></td>
        <td>{{ (a.confidence*100)|round(0) }}%</td>
        <td>{{ a.reason or '—' }}</td>
        <td>{% if a.notified %}✓{% else %}—{% endif %}</td>
        <td>
          {% if not a.parent_acknowledged %}
          <form method="post" action="/web/toxic-alerts/{{ a.id }}/ack" style="display:inline">
            <button class="btn btn-sm">确认</button>
          </form>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="muted">没有毒视频告警，孩子浏览内容正常 🎉</p>
  {% endif %}
</div>
{% endblock %}
''')

# === Weekly reports ===
write_file("app/web/templates/weekly_reports.html", '''{% extends "_layout.html" %}
{% block heading %}周报{% endblock %}
{% set active = 'reports' %}
{% block content %}
<div class="panel">
  {% if reports %}
  <table class="table">
    <thead><tr><th>周</th><th>成员</th><th>总时长</th><th>答题次数</th><th>正确率</th><th>推送</th><th></th></tr></thead>
    <tbody>
      {% for r in reports %}
      <tr>
        <td>{{ r.week_start }} ~ {{ r.week_end }}</td>
        <td>{{ r.member_name }}</td>
        <td>{{ r.summary.total_minutes or 0 }} 分钟</td>
        <td>{{ r.summary.quiz_count or 0 }}</td>
        <td>{{ ((r.summary.overall_accuracy or 0)*100)|round(0) }}%</td>
        <td>{% if r.push_status=='sent' %}<span class="badge badge-ok">已发送</span>{% elif r.push_status=='failed' %}<span class="badge badge-warn">失败</span>{% else %}<span class="badge badge-muted">待推送</span>{% endif %}</td>
        <td><a href="/web/weekly-reports/{{ r.id }}" class="btn btn-sm">查看</a></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="muted">还没有周报。系统会在每周日 20:00 自动生成。</p>
  {% endif %}
</div>
{% endblock %}
''')

# === Settings (push config) ===
write_file("app/web/templates/settings.html", '''{% extends "_layout.html" %}
{% block heading %}推送设置{% endblock %}
{% set active = 'settings' %}
{% block content %}
<div class="panel">
  <form method="post" action="/web/settings" class="form">
    <h3 class="panel-title">邮件推送</h3>
    <label class="field"><span>收件邮箱</span><input name="email" type="email" value="{{ cfg.email or '' }}" /></label>
    <label class="field"><span>SMTP 主机</span><input name="smtp_host" value="{{ cfg.smtp_host or '' }}" /></label>
    <label class="field"><span>SMTP 端口</span><input name="smtp_port" type="number" value="{{ cfg.smtp_port or 587 }}" /></label>
    <label class="field"><span>SMTP 用户名</span><input name="smtp_user" value="{{ cfg.smtp_user or '' }}" /></label>
    <label class="field"><span>SMTP 密码</span><input name="smtp_password" type="password" /></label>
    <label class="field"><span>毒视频告警阈值 (0-1)</span><input name="toxic_threshold" type="number" step="0.05" min="0" max="1" value="{{ cfg.toxic_alert_threshold or 0.7 }}" /></label>
    <label class="checkbox"><input type="checkbox" name="enable_weekly_email" {% if cfg.enable_weekly_email %}checked{% endif %} /> 启用每周邮件推送</label>
    <label class="checkbox"><input type="checkbox" name="enable_toxic_alert" {% if cfg.enable_toxic_alert %}checked{% endif %} /> 启用毒视频即时告警</label>

    <h3 class="panel-title">Webhook（企业微信/钉钉/Slack）</h3>
    <label class="field"><span>Webhook URL</span><input name="webhook_url" value="{{ cfg.webhook_url or '' }}" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." /></label>

    <button type="submit" class="btn btn-primary">保存</button>
  </form>
</div>
{% endblock %}
''')

print("\nTemplates done.")