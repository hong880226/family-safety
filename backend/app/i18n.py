"""Translation strings.

v0.1: 仅 zh-CN。后续要加 en-US 时，把每个 key 在这里补一份；模板用
`{{ t("key") }}` 替代硬编码字符串。
"""
from typing import Literal

Lang = Literal["zh-CN", "en-US"]

_STRINGS: dict[str, dict[str, str]] = {
    # ---- Auth ----
    "auth.login.title": {"zh-CN": "登录", "en-US": "Sign in"},
    "auth.login.username": {"zh-CN": "用户名", "en-US": "Username"},
    "auth.login.password": {"zh-CN": "密码", "en-US": "Password"},
    "auth.login.submit": {"zh-CN": "登录", "en-US": "Sign in"},
    "auth.login.failed": {"zh-CN": "用户名或密码错误", "en-US": "Invalid credentials"},
    "auth.logout": {"zh-CN": "退出", "en-US": "Sign out"},
    "auth.password.change": {"zh-CN": "修改密码", "en-US": "Change password"},
    "auth.password.current": {"zh-CN": "当前密码", "en-US": "Current password"},
    "auth.password.new": {"zh-CN": "新密码", "en-US": "New password"},
    "auth.password.confirm": {"zh-CN": "确认新密码", "en-US": "Confirm new password"},
    "auth.password.mismatch": {"zh-CN": "两次输入的新密码不一致",
                                "en-US": "New passwords do not match"},
    "auth.password.too_short": {"zh-CN": "新密码至少 8 个字符",
                                "en-US": "Password must be at least 8 characters"},
    "auth.password.wrong_current": {"zh-CN": "当前密码错误",
                                    "en-US": "Current password is incorrect"},

    # ---- Navigation ----
    "nav.dashboard": {"zh-CN": "概览", "en-US": "Dashboard"},
    "nav.members": {"zh-CN": "成员", "en-US": "Members"},
    "nav.devices": {"zh-CN": "设备", "en-US": "Devices"},
    "nav.rules": {"zh-CN": "规则", "en-US": "Rules"},
    "nav.quiz": {"zh-CN": "答题配置", "en-US": "Quiz"},
    "nav.mastery": {"zh-CN": "弱项分析", "en-US": "Mastery"},
    "nav.content": {"zh-CN": "内容规则", "en-US": "Content rules"},
    "nav.toxic": {"zh-CN": "毒视频告警", "en-US": "Toxic alerts"},
    "nav.reports": {"zh-CN": "周报", "en-US": "Weekly reports"},
    "nav.settings": {"zh-CN": "推送设置", "en-US": "Notifications"},

    # ---- Errors ----
    "error.404.title": {"zh-CN": "页面不存在", "en-US": "Page not found"},
    "error.404.body": {"zh-CN": "你访问的页面不存在或已被删除。",
                       "en-US": "The page you requested does not exist."},
    "error.500.title": {"zh-CN": "服务暂时不可用", "en-US": "Service unavailable"},
    "error.500.body": {"zh-CN": "请稍后重试。", "en-US": "Please try again later."},
    "error.csrf": {"zh-CN": "会话已过期，请刷新页面重试。",
                   "en-US": "Session expired; please refresh and try again."},
}


_DEFAULT_LANG: Lang = "zh-CN"


def t(key: str, lang: Lang = _DEFAULT_LANG) -> str:
    """Resolve a translation key. Falls back to zh-CN, then to the key itself."""
    entry = _STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get(_DEFAULT_LANG) or key