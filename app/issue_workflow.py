"""Issue status and elapsed-time rules shared by views and the API."""

from __future__ import annotations

from datetime import datetime

from .extensions import db
from .models import Cell, Issue, utcnow
from .services import audit, render_markdown


ISSUE_STATUSES = ("未处理", "处理中", "等待中", "待验证", "已解决")
PRIORITIES = ("高", "普通", "低")
CELL_KINDS = ("普通记录", "现象", "测试记录", "当前判断", "下一步待办", "等待原因", "阶段结论", "结论及复盘", "知识积累")
CELL_STATUS = {
    "现象": "处理中",
    "测试记录": "处理中",
    "当前判断": "处理中",
    "等待原因": "等待中",
    "阶段结论": "待验证",
    "结论及复盘": "已解决",
}


def elapsed_seconds(issue: Issue, now: datetime | None = None) -> int:
    end = issue.resolved_at if issue.status == "已解决" and issue.resolved_at else (now or utcnow())
    return max(int((end - issue.created_at).total_seconds()), 0)


def duration_label(seconds: int) -> str:
    days, remainder = divmod(max(seconds, 0), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return f"{days}天 {hours}小时"
    if hours:
        return f"{hours}小时 {minutes}分钟"
    if minutes:
        return f"{minutes}分钟"
    return "不足1分钟"


def set_issue_status(issue: Issue, new_status: str, *, user_id: int, source: str) -> bool:
    if new_status not in ISSUE_STATUSES:
        raise ValueError("无效的问题状态。")
    old_status = issue.status
    if old_status == new_status:
        return False
    changed_at = utcnow()
    issue.status = new_status
    issue.resolved_at = changed_at if new_status == "已解决" else None
    issue.updated_at = changed_at
    text = f"{old_status} → {new_status}"
    db.session.add(Cell(issue=issue, kind="状态变化", content_md=text, rendered_html=render_markdown(text), author_id=user_id))
    audit("issue.status_change", issue, detail=f"{text} ({source})")
    return True


def apply_cell_status(issue: Issue, kind: str, *, user_id: int) -> bool:
    if kind not in CELL_KINDS:
        raise ValueError("无效的 Cell 类型。")
    target = CELL_STATUS.get(kind)
    if not target or (issue.status == "已解决" and target != "已解决"):
        return False
    return set_issue_status(issue, target, user_id=user_id, source=f"Cell:{kind}")
