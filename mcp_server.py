"""Read-only MCP interface for local Codex access to BoardTrace records."""

from __future__ import annotations

import sqlite3
import warnings
from datetime import date, timedelta
from pathlib import Path

warnings.filterwarnings("ignore", message="Field 'lifespan' has an incomplete definition.*")

from mcp.server.fastmcp import FastMCP


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "app.db"
MAX_LIMIT = 100
MAX_TEXT = 20_000

mcp = FastMCP(
    "boardtrace-readonly",
    instructions="Read-only, paginated access to the local PCB work-record database. Never modifies data.",
    log_level="WARNING",
)


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError("数据库尚未创建，请先启动网站并完成初始化。")
    connection = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _limit(value: int) -> int:
    return max(1, min(int(value), MAX_LIMIT))


def _clean(rows) -> list[dict]:
    result = []
    used = 0
    for row in rows:
        item = dict(row)
        for key, value in item.items():
            if isinstance(value, str) and len(value) > 4_000:
                item[key] = value[:4_000] + "…"
        size = len(str(item))
        if result and used + size > MAX_TEXT:
            break
        result.append(item)
        used += size
    return result


@mcp.tool()
def search_records(query: str, limit: int = 20) -> dict:
    """Search projects, PCBs, issues, all Cells, knowledge, and work records."""
    query = (query or "").strip()
    if not query:
        return {"query": query, "results": [], "note": "请输入搜索词。"}
    take = _limit(limit)
    like = f"%{query}%"
    sql = """
    SELECT * FROM (
      SELECT 'pcb' AS type, id, serial AS title, (model || ' ' || revision || ' ' || notes) AS content,
             updated_at AS occurred_at, NULL AS parent_id
      FROM pcbs WHERE deleted_at IS NULL AND (serial LIKE ? OR model LIKE ? OR revision LIKE ? OR notes LIKE ?)
      UNION ALL
      SELECT 'issue', id, title, (description || ' ' || current_summary || ' ' || tags), updated_at, pcb_id
      FROM issues WHERE deleted_at IS NULL AND (title LIKE ? OR description LIKE ? OR current_summary LIKE ? OR tags LIKE ?)
      UNION ALL
      SELECT 'cell', cells.id, cells.kind, cells.content_md, cells.created_at, cells.issue_id
      FROM cells WHERE cells.deleted_at IS NULL AND cells.content_md LIKE ?
      UNION ALL
      SELECT CASE WHEN pcb_id IS NOT NULL THEN 'pcb_cell' ELSE 'project_cell' END,
             id, kind, content_md, created_at, COALESCE(pcb_id, project_id)
      FROM object_cells WHERE deleted_at IS NULL AND content_md LIKE ?
      UNION ALL
      SELECT 'project', id, name, (objective || ' ' || next_action), updated_at, NULL
      FROM projects WHERE deleted_at IS NULL AND (name LIKE ? OR objective LIKE ? OR next_action LIKE ?)
      UNION ALL
      SELECT 'knowledge', id, title, content_md, updated_at, source_issue_id
      FROM knowledge_entries WHERE deleted_at IS NULL AND (title LIKE ? OR content_md LIKE ?)
      UNION ALL
      SELECT 'work', id, title, (content || ' ' || result || ' ' || next_step), created_at, pcb_id
      FROM work_logs WHERE deleted_at IS NULL AND (title LIKE ? OR content LIKE ? OR result LIKE ? OR next_step LIKE ?)
    ) ORDER BY occurred_at DESC LIMIT ?
    """
    params = [like] * 4 + [like] * 4 + [like] + [like] + [like] * 3 + [like] * 2 + [like] * 4 + [take]
    with _connect() as connection:
        rows = connection.execute(sql, params).fetchall()
    return {"query": query, "results": _clean(rows), "limit": take}


@mcp.tool()
def get_knowledge(entry_id: int) -> dict:
    """Read one knowledge note with its source issue, bounded to a safe response size."""
    with _connect() as connection:
        row = connection.execute(
            """SELECT knowledge_entries.id,knowledge_entries.title,knowledge_entries.content_md,
                      knowledge_entries.created_at,knowledge_entries.updated_at,
                      knowledge_entries.source_issue_id,issues.title AS source_issue_title
               FROM knowledge_entries LEFT JOIN issues ON issues.id=knowledge_entries.source_issue_id
               WHERE knowledge_entries.id=? AND knowledge_entries.deleted_at IS NULL""",
            (entry_id,),
        ).fetchone()
    return {"knowledge": _clean([row])[0] if row else None}


@mcp.tool()
def get_pcb_history(serial: str, limit: int = 20, before_id: int | None = None) -> dict:
    """Return one PCB and its latest issues, direct Cells, and work records."""
    take = _limit(limit)
    with _connect() as connection:
        pcb = connection.execute(
            "SELECT id,serial,model,revision,status,notes,created_at,updated_at FROM pcbs WHERE deleted_at IS NULL AND lower(serial)=lower(?)",
            ((serial or "").strip(),),
        ).fetchone()
        if not pcb:
            return {"pcb": None, "items": [], "note": "未找到该PCB序列号。"}
        cursor_sql = " AND source_id < ?" if before_id else ""
        sql = f"""
        SELECT * FROM (
          SELECT id AS source_id, 'issue' AS type, title, (status || ' / ' || priority) AS summary,
                 updated_at AS occurred_at FROM issues WHERE deleted_at IS NULL AND pcb_id=?
          UNION ALL
          SELECT id, 'work', title, (result || ' · ' || minutes || '分钟'), created_at
                 FROM work_logs WHERE deleted_at IS NULL AND pcb_id=?
          UNION ALL
          SELECT id, 'pcb_cell', kind, content_md, created_at
                 FROM object_cells WHERE deleted_at IS NULL AND pcb_id=?
        ) WHERE 1=1 {cursor_sql} ORDER BY occurred_at DESC, source_id DESC LIMIT ?
        """
        params = [pcb["id"], pcb["id"], pcb["id"]]
        if before_id:
            params.append(before_id)
        params.append(take)
        rows = connection.execute(sql, params).fetchall()
    items = _clean(rows)
    return {"pcb": dict(pcb), "items": items, "next_before": items[-1]["source_id"] if len(items) == take else None}


@mcp.tool()
def get_project_history(project_id: int, limit: int = 20, before_id: int | None = None) -> dict:
    """Return one project, its linked PCBs, and latest project Cells and issues."""
    take = _limit(limit)
    with _connect() as connection:
        project = connection.execute(
            "SELECT id,name,objective,status,next_action,created_at,updated_at FROM projects WHERE id=? AND deleted_at IS NULL",
            (project_id,),
        ).fetchone()
        if not project:
            return {"project": None, "pcbs": [], "items": [], "note": "项目不存在或已进入回收站。"}
        pcbs = connection.execute(
            """SELECT pcbs.id,pcbs.model,pcbs.serial,pcbs.revision,pcbs.status
               FROM project_pcbs JOIN pcbs ON pcbs.id=project_pcbs.pcb_id
               WHERE project_pcbs.project_id=? AND pcbs.deleted_at IS NULL
               ORDER BY pcbs.model,pcbs.serial""",
            (project_id,),
        ).fetchall()
        cursor_sql = " AND source_id < ?" if before_id else ""
        sql = f"""
        SELECT * FROM (
          SELECT id AS source_id, 'project_cell' AS type, kind AS title, content_md AS summary,
                 created_at AS occurred_at FROM object_cells
                 WHERE deleted_at IS NULL AND project_id=?
          UNION ALL
          SELECT id, 'issue', title, (status || ' / ' || priority), updated_at
                 FROM issues WHERE deleted_at IS NULL AND project_id=?
        ) WHERE 1=1 {cursor_sql} ORDER BY occurred_at DESC, source_id DESC LIMIT ?
        """
        params = [project_id, project_id]
        if before_id:
            params.append(before_id)
        params.append(take)
        rows = connection.execute(sql, params).fetchall()
    items = _clean(rows)
    return {"project": dict(project), "pcbs": _clean(pcbs), "items": items,
            "next_before": items[-1]["source_id"] if len(items) == take else None}


@mcp.tool()
def get_issue(issue_id: int, limit: int = 20, before_id: int | None = None) -> dict:
    """Return an issue plus a page of newest-first Cells and attachment metadata."""
    take = _limit(limit)
    with _connect() as connection:
        issue = connection.execute(
            """SELECT issues.id,issues.title,issues.description,issues.current_summary,issues.status,issues.priority,
                      issues.tags,issues.created_at,issues.updated_at,issues.resolved_at,
                      pcbs.serial AS pcb_serial,projects.name AS project_name
               FROM issues LEFT JOIN pcbs ON pcbs.id=issues.pcb_id LEFT JOIN projects ON projects.id=issues.project_id
               WHERE issues.id=? AND issues.deleted_at IS NULL""",
            (issue_id,),
        ).fetchone()
        if not issue:
            return {"issue": None, "cells": [], "note": "问题不存在或已进入回收站。"}
        sql = """SELECT cells.id,cells.kind,cells.content_md,cells.created_at,users.username,
                        (SELECT count(*) FROM attachments WHERE attachments.cell_id=cells.id AND attachments.deleted_at IS NULL) AS attachment_count
                 FROM cells LEFT JOIN users ON users.id=cells.author_id
                 WHERE cells.issue_id=? AND cells.deleted_at IS NULL"""
        params: list[object] = [issue_id]
        if before_id:
            sql += " AND cells.id < ?"
            params.append(before_id)
        sql += " ORDER BY cells.id DESC LIMIT ?"
        params.append(take)
        cells = connection.execute(sql, params).fetchall()
    clean_cells = _clean(cells)
    return {"issue": dict(issue), "cells": clean_cells, "next_before": clean_cells[-1]["id"] if len(clean_cells) == take else None}


@mcp.tool()
def list_recent_work(days: int = 7, limit: int = 20) -> dict:
    """List recent work logs with PCB, project, issue, result, next step, and minutes."""
    take = _limit(limit)
    days = max(1, min(int(days), 366))
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    with _connect() as connection:
        rows = connection.execute(
            """SELECT work_logs.id,work_logs.title,work_logs.content,work_logs.result,work_logs.next_step,
                      work_logs.minutes,work_logs.created_at,pcbs.serial AS pcb_serial,projects.name AS project_name,issues.title AS issue_title
               FROM work_logs LEFT JOIN pcbs ON pcbs.id=work_logs.pcb_id LEFT JOIN projects ON projects.id=work_logs.project_id
               LEFT JOIN issues ON issues.id=work_logs.issue_id
               WHERE work_logs.deleted_at IS NULL AND date(work_logs.created_at)>=date(?)
               ORDER BY work_logs.created_at DESC LIMIT ?""",
            (since, take),
        ).fetchall()
    return {"days": days, "records": _clean(rows), "limit": take}


@mcp.tool()
def build_ai_context(pcb_serial: str = "", issue_id: int = 0, project_id: int = 0, limit: int = 20) -> dict:
    """Build a compact context bundle for one project, PCB, or issue."""
    if issue_id:
        return get_issue(issue_id, limit)
    if pcb_serial.strip():
        return get_pcb_history(pcb_serial, limit)
    if project_id:
        return get_project_history(project_id, limit)
    return {"error": "请提供 project_id、pcb_serial 或 issue_id。"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
