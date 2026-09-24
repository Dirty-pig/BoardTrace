from io import BytesIO

from PIL import Image

from app.models import Attachment, AuditLog, Cell, Issue, PCB, User
from app.services import run_backup


def sample_png():
    stream = BytesIO()
    Image.new("RGB", (80, 60), "#4f7cff").save(stream, "PNG")
    stream.seek(0)
    return stream


def test_first_run_redirects_to_initialization(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/initialize" in response.headers["Location"]


def test_root_initialization_and_dashboard(app, initialized_client):
    response = initialized_client.get("/")
    assert response.status_code == 200
    assert "板迹测试" in response.get_data(as_text=True)
    with app.app_context():
        user = User.query.one()
        assert user.role == "root"
        assert user.password_hash.startswith("$argon2")


def test_pcb_issue_cell_image_and_api(app, initialized_client):
    response = initialized_client.post("/pcbs", data={"serial": "PCB-2026-0001", "model": "CTRL-A", "revision": "V1.2"})
    assert response.status_code == 302
    with app.app_context():
        pcb = PCB.query.filter_by(serial="PCB-2026-0001").one()
        pcb_id = pcb.id

    listing = initialized_client.get("/pcbs").get_data(as_text=True)
    assert listing.index("CTRL-A") < listing.index("PCB-2026-0001")
    detail = initialized_client.get(f"/pcbs/{pcb_id}").get_data(as_text=True)
    assert "<h1>CTRL-A</h1>" in detail

    issues_page = initialized_client.get("/issues").get_data(as_text=True)
    assert "<span>板卡型号（可选）</span>" in issues_page
    assert "CTRL-A · 版本号：V1.2 · PCB序列号：PCB-2026-0001" in issues_page
    assert "<span>▤</span>板卡型号</a>" in issues_page

    response = initialized_client.post("/issues", data={
        "title": "上电后电源纹波偏高", "description": "测得 **48mV**", "status": "处理中", "priority": "高", "pcb_id": pcb_id,
    })
    assert response.status_code == 302
    with app.app_context():
        issue = Issue.query.filter_by(title="上电后电源纹波偏高").one()
        issue_id = issue.id
        assert issue.cells.count() == 1

    issues_page = initialized_client.get("/issues").get_data(as_text=True)
    assert issues_page.index("CTRL-A") < issues_page.index("PCB-2026-0001")

    response = initialized_client.post(
        f"/issues/{issue_id}/cells",
        data={"kind": "测试记录", "content": "[red]纹波超标[/red]，准备更换电容", "attachments": (sample_png(), "scope.png")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "纹波超标" in response.get_data(as_text=True)
    with app.app_context():
        assert Cell.query.filter_by(issue_id=issue_id).count() == 2
        attachment = Attachment.query.one()
        assert attachment.size > 0
        assert attachment.thumbnail_name
        attachment_id = attachment.id

    page = initialized_client.get(f"/issues/{issue_id}").get_data(as_text=True)
    assert page.index('class="composer backend-composer"') < page.index('class="chat-stream"')
    assert f'/attachments/{attachment_id}/view' in page
    assert 'data-preview-url=' in page
    image_view = initialized_client.get(f"/attachments/{attachment_id}/view")
    assert image_view.status_code == 200
    assert image_view.headers["Content-Disposition"].startswith("inline")

    response = initialized_client.get(f"/api/v1/issues/{issue_id}?limit=1")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["issue"]["title"] == "上电后电源纹波偏高"
    assert len(payload["cells"]) == 1
    assert payload["next_before"] is not None


def test_login_lockout_is_audited(app, initialized_client):
    initialized_client.post("/logout")
    for _ in range(5):
        response = initialized_client.post("/login", data={"username": "root", "password": "wrong"})
        assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(username="root").one()
        assert user.locked_until is not None
        assert AuditLog.query.filter_by(action="auth.login_failed").count() == 5


def test_backup_is_consistent(app, initialized_client, tmp_path):
    initialized_client.post("/pcbs", data={"serial": "BACKUP-PCB"})
    with app.app_context():
        location, manifest = run_backup(tmp_path / "external-backup")
        assert (location / "app.db").exists()
        assert (location / "manifest.json").exists()
        assert len(manifest["database_sha256"]) == 64


def test_authenticated_pages_and_security_headers(initialized_client):
    for path in ["/", "/pcbs", "/projects", "/issues", "/work", "/search", "/trash", "/admin"]:
        response = initialized_client.get(path)
        assert response.status_code == 200, path
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_markdown_table_is_rendered_and_sanitized():
    from app.services import render_markdown

    html = render_markdown("| 型号 | 电压 |\n| --- | --- |\n| S1485 | 3.3V |")
    assert "<table>" in html
    assert "<th>型号</th>" in html
    assert "<td>3.3V</td>" in html
    assert "<script>" not in render_markdown("<script>alert(1)</script>")


def test_issue_cell_can_be_trashed_and_restored_with_attachment(app, initialized_client):
    initialized_client.post("/issues", data={"title": "可撤销的记录"})
    with app.app_context():
        issue_id = Issue.query.filter_by(title="可撤销的记录").one().id
    initialized_client.post(
        f"/issues/{issue_id}/cells",
        data={"kind": "测试记录", "content": "误写的测量值", "attachments": (sample_png(), "scope.png")},
        content_type="multipart/form-data",
    )
    with app.app_context():
        cell = Cell.query.filter_by(issue_id=issue_id, kind="测试记录").one()
        cell_id = cell.id
        attachment_id = cell.attachments.one().id
        status_before = cell.issue.status
    page = initialized_client.get(f"/issues/{issue_id}").get_data(as_text=True)
    assert f"/issues/{issue_id}/cells/{cell_id}/trash" in page
    assert initialized_client.post(f"/issues/{issue_id + 1}/cells/{cell_id}/trash").status_code == 404
    response = initialized_client.post(f"/issues/{issue_id}/cells/{cell_id}/trash", follow_redirects=True)
    assert response.status_code == 200
    assert "误写的测量值" not in response.get_data(as_text=True)
    assert initialized_client.get(f"/issues/{issue_id}?cell={cell_id}").status_code == 404
    assert initialized_client.get(f"/attachments/{attachment_id}/view").status_code == 404
    with app.app_context():
        assert Cell.query.get(cell_id).deleted_at is not None
        assert Attachment.query.get(attachment_id).deleted_at is not None
        assert Issue.query.get(issue_id).status == status_before
    assert f"/trash/restore/cell/{cell_id}" in initialized_client.get("/trash").get_data(as_text=True)
    initialized_client.post(f"/trash/restore/cell/{cell_id}")
    assert initialized_client.get(f"/issues/{issue_id}?cell={cell_id}").status_code == 200
    assert initialized_client.get(f"/attachments/{attachment_id}/view").status_code == 200
    assert initialized_client.post(f"/issues/{issue_id}/cells/{cell_id}/trash").status_code == 302
    assert initialized_client.post(f"/issues/{issue_id}/cells/{cell_id}/trash").status_code == 404
