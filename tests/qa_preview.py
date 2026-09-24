"""Manual visual-QA server. Uses an in-memory database and never touches real data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from argon2 import PasswordHasher
from waitress import serve

from app import create_app
from app.extensions import db
from app.models import Cell, Issue, ObjectCell, PCB, Project, User, WorkLog
from app.services import render_markdown


app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "WTF_CSRF_ENABLED": False})
with app.app_context():
    root = User(username="qa-root", password_hash=PasswordHasher().hash("qa-password-only"), role="root")
    db.session.add(root)
    db.session.flush()
    pcb = PCB(serial="PCB-2026-0047", model="Control Board", revision="V1.3", status="处理中", notes="电源与接口联调", created_by_id=root.id)
    db.session.add(pcb)
    db.session.flush()
    second_pcb = PCB(serial="PCB-2026-0048", model="Control Board", revision="V1.3", status="处理中", notes="对比样板", created_by_id=root.id)
    project = Project(name="Control Board 联调", objective="完成两块样板的电源和接口联调", status="进行中", created_by_id=root.id)
    project.pcbs.extend([pcb, second_pcb])
    db.session.add_all([second_pcb, project])
    db.session.flush()
    issue = Issue(title="上电后 3V3 纹波偶发偏高", description="冷启动时观察到瞬态纹波。", current_summary="正在对比电容批次和负载条件。", status="待验证", priority="高", pcb=pcb, project=project, created_by_id=root.id, tags="电源,纹波")
    db.session.add(issue)
    db.session.flush()
    for kind, content in [
        ("现象", "冷启动前 200ms 出现 **48mV** 峰值。"),
        ("测试记录", "[orange]更换 C37 后复测 10 次[/orange]，其中 1 次仍复现。"),
        ("下一步待办", "提高负载阶跃幅度，并记录示波器原始波形。"),
    ]:
        db.session.add(Cell(issue=issue, kind=kind, content_md=content, rendered_html=render_markdown(content), author_id=root.id))
    db.session.add(ObjectCell(project=project, kind="阶段结论", content_md="两块样板已完成基础上电验证。", rendered_html=render_markdown("两块样板已完成基础上电验证。"), author_id=root.id))
    db.session.add(ObjectCell(pcb=pcb, kind="测试记录", content_md="3V3 纹波复测为 31mV。", rendered_html=render_markdown("3V3 纹波复测为 31mV。"), author_id=root.id))
    db.session.add(WorkLog(title="复测 3V3 电源", content="更换电容并重复冷启动", result="复现率下降", next_step="扩大样本", minutes=65, pcb=pcb, issue=issue, user_id=root.id))
    db.session.commit()


if __name__ == "__main__":
    serve(app, host="127.0.0.1", port=5001, threads=4)
