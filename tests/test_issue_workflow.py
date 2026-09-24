from datetime import timedelta

from app.issue_workflow import elapsed_seconds
from app.models import Cell, Issue, utcnow


def _new_issue(client):
    response = client.post("/issues", data={"title": "上电异常", "priority": "普通"})
    assert response.status_code == 302
    return int(response.headers["Location"].rstrip("/").split("/")[-1])


def test_elapsed_time_cell_filter_and_status_transitions(app, initialized_client):
    issue_id = _new_issue(initialized_client)
    with app.app_context():
        issue = Issue.query.get(issue_id)
        assert issue.status == "未处理"
        issue.created_at = utcnow() - timedelta(hours=2)
        app.extensions["sqlalchemy"].session.commit()
        assert elapsed_seconds(issue) >= 7200

    response = initialized_client.get(f"/issues/{issue_id}")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "2小时" in page
    assert "单独查看" in page or "筛选 Cell" in page

    for kind, expected in [
        ("测试记录", "处理中"), ("等待原因", "等待中"),
        ("阶段结论", "待验证"), ("结论及复盘", "已解决"),
    ]:
        response = initialized_client.post(f"/issues/{issue_id}/cells", data={"kind": kind, "content": kind})
        assert response.status_code == 302
        with app.app_context():
            issue = Issue.query.get(issue_id)
            assert issue.status == expected
            assert (issue.resolved_at is not None) == (expected == "已解决")
    with app.app_context():
        issue = Issue.query.get(issue_id)
        solved_seconds = elapsed_seconds(issue)
        filtered_cell = issue.cells.filter_by(kind="等待原因").one()
        cell_id = filtered_cell.id
        assert issue.cells.filter_by(kind="状态变化").count() == 4

    filtered = initialized_client.get(f"/issues/{issue_id}?kind=等待原因").get_data(as_text=True)
    assert "正在单独查看" not in filtered
    assert "该类型暂无" not in filtered
    focused = initialized_client.get(f"/issues/{issue_id}?cell={cell_id}").get_data(as_text=True)
    assert f"正在单独查看 Cell #{cell_id}" in focused
    assert initialized_client.get(f"/issues/{issue_id}?cell=99999").status_code == 404
    assert initialized_client.get(f"/issues/{issue_id}?kind=无效").status_code == 400
    with app.app_context():
        issue = Issue.query.get(issue_id)
        assert elapsed_seconds(issue, now=utcnow() + timedelta(days=1)) == solved_seconds


def test_direct_state_edits_and_reopen(app, initialized_client):
    issue_id = _new_issue(initialized_client)
    response = initialized_client.post(f"/issues/{issue_id}/state", data={"field": "priority", "value": "高"})
    assert response.status_code == 302
    response = initialized_client.post(f"/issues/{issue_id}/state", data={"field": "status", "value": "已解决"})
    assert response.status_code == 302
    with app.app_context():
        issue = Issue.query.get(issue_id)
        assert issue.priority == "高"
        assert issue.resolved_at is not None

    initialized_client.post(f"/issues/{issue_id}/cells", data={"kind": "测试记录", "content": "补充资料"})
    with app.app_context():
        assert Issue.query.get(issue_id).status == "已解决"
    initialized_client.post(f"/issues/{issue_id}/state", data={"field": "status", "value": "处理中"})
    with app.app_context():
        issue = Issue.query.get(issue_id)
        assert issue.status == "处理中"
        assert issue.resolved_at is None
    assert initialized_client.post(f"/issues/{issue_id}/state", data={"field": "priority", "value": "紧急"}).status_code == 400
    assert initialized_client.post(f"/issues/{issue_id}/cells", data={"kind": "不存在", "content": "x"}).status_code == 400


def test_generated_state_change_cell_cannot_be_deleted(app, initialized_client):
    issue_id = _new_issue(initialized_client)
    initialized_client.post(f"/issues/{issue_id}/state", data={"field": "status", "value": "处理中"})
    with app.app_context():
        cell_id = Cell.query.filter_by(issue_id=issue_id, kind="状态变化").one().id
    assert f"/issues/{issue_id}/cells/{cell_id}/trash" not in initialized_client.get(f"/issues/{issue_id}").get_data(as_text=True)
    assert initialized_client.post(f"/issues/{issue_id}/cells/{cell_id}/trash").status_code == 400
