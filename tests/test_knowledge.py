def test_knowledge_cell_is_searchable_and_keeps_an_issue_link(app, initialized_client):
    created = initialized_client.post("/issues", data={"title": "接口干扰"})
    issue_id = int(created.headers["Location"].rstrip("/").split("/")[-1])

    response = initialized_client.post(
        f"/issues/{issue_id}/cells",
        data={"kind": "知识积累", "title": "示波器探头接地", "content": "短地弹簧可减少 <script>alert(1)</script> 测量伪影。"},
    )
    assert response.status_code == 302
    issue_page = initialized_client.get(f"/issues/{issue_id}").get_data(as_text=True)
    assert "示波器探头接地" in issue_page
    assert "知识积累" in issue_page

    library = initialized_client.get("/knowledge?q=探头").get_data(as_text=True)
    assert "示波器探头接地" in library
    assert "接口干扰" in library
    assert "示波器探头接地" not in initialized_client.get("/knowledge?q=电源轨").get_data(as_text=True)
    assert "<script>" not in library
    assert "示波器探头接地" in initialized_client.get("/search?q=探头").get_data(as_text=True)
    assert any(row["type"] == "knowledge" for row in initialized_client.get("/api/v1/search?q=探头").json)

    with app.app_context():
        from app.models import KnowledgeEntry

        entries = KnowledgeEntry.query.all()
        assert len(entries) == 1
        assert entries[0].source_issue_id == issue_id
        assert entries[0].title == "示波器探头接地"
        entry_id = entries[0].id

    detail = initialized_client.get(f"/knowledge/{entry_id}").get_data(as_text=True)
    assert "示波器探头接地" in detail
    assert "<script>" not in detail
    response = initialized_client.post(
        f"/knowledge/{entry_id}/update", data={"title": "低感接地方法", "content": "使用短地弹簧。"}
    )
    assert response.status_code == 302
    assert "低感接地方法" in initialized_client.get(f"/issues/{issue_id}").get_data(as_text=True)
    assert initialized_client.get("/api/v1/knowledge?q=低感").json["items"][0]["title"] == "低感接地方法"


def test_standalone_knowledge_title_required_and_list_paginated(app, initialized_client):
    assert initialized_client.post("/knowledge", data={"title": "", "content": "正文"}).status_code != 500
    with app.app_context():
        from app.models import KnowledgeEntry

        assert KnowledgeEntry.query.count() == 0

    for number in range(23):
        response = initialized_client.post(
            "/knowledge", data={"title": f"知识 {number:02}", "content": "复用的处理办法"}
        )
        assert response.status_code == 302

    first_page = initialized_client.get("/knowledge")
    assert first_page.status_code == 200
    assert first_page.get_data(as_text=True).count('class="knowledge-row"') == 20
    second_page = initialized_client.get("/knowledge?page=2")
    assert second_page.status_code == 200
    assert second_page.get_data(as_text=True).count('class="knowledge-row"') == 3


def test_knowledge_requires_login(client):
    assert client.get("/knowledge").status_code == 302
    assert client.post("/knowledge", data={"title": "不应写入", "content": "x"}).status_code == 302


def test_deleting_source_cell_keeps_independent_knowledge(app, initialized_client):
    from app.models import Cell, KnowledgeEntry

    created = initialized_client.post("/issues", data={"title": "来源问题"})
    issue_id = int(created.headers["Location"].rstrip("/").split("/")[-1])
    initialized_client.post(
        f"/issues/{issue_id}/cells",
        data={"kind": "知识积累", "title": "保留的知识", "content": "独立正文"},
    )
    with app.app_context():
        entry = KnowledgeEntry.query.one()
        cell_id, entry_id = entry.source_cell_id, entry.id
    assert initialized_client.post(f"/issues/{issue_id}/cells/{cell_id}/trash").status_code == 302
    assert initialized_client.get(f"/issues/{issue_id}?cell={cell_id}").status_code == 404
    assert "独立正文" in initialized_client.get(f"/knowledge/{entry_id}").get_data(as_text=True)
    with app.app_context():
        assert Cell.query.get(cell_id).deleted_at is not None
        assert KnowledgeEntry.query.get(entry_id).deleted_at is None


def test_knowledge_can_link_to_issue_and_show_practice(app, initialized_client):
    from app.models import KnowledgeEntry

    created = initialized_client.post("/issues", data={"title": "电源纹波异常", "description": "上电后测得纹波偏高"})
    issue_id = int(created.headers["Location"].rstrip("/").split("/")[-1])
    initialized_client.post(
        f"/issues/{issue_id}/cells", data={"kind": "测试记录", "content": "更换探头接地方式后复测"}
    )
    response = initialized_client.post(
        "/knowledge",
        data={"title": "降低测量伪影", "content": "使用短地弹簧。", "issue_ref": f"#{issue_id} · 电源纹波异常"},
    )
    assert response.status_code == 302
    with app.app_context():
        entry = KnowledgeEntry.query.filter_by(title="降低测量伪影").one()
        entry_id = entry.id
        assert entry.source_issue_id == issue_id
        assert entry.source_cell_id is None

    detail = initialized_client.get(f"/knowledge/{entry_id}").get_data(as_text=True)
    assert "电源纹波异常" in detail
    assert "上电后测得纹波偏高" in detail
    assert "更换探头接地方式后复测" in detail
    assert f"/issues/{issue_id}?cell=" in detail
    issue_page = initialized_client.get(f"/issues/{issue_id}").get_data(as_text=True)
    assert "相关知识" in issue_page and "降低测量伪影" in issue_page
    filtered = initialized_client.get(f"/knowledge?issue_id={issue_id}").get_data(as_text=True)
    assert "降低测量伪影" in filtered

    response = initialized_client.post(
        f"/knowledge/{entry_id}/update",
        data={"title": "降低测量伪影", "content": "使用短地弹簧。", "issue_ref": ""},
    )
    assert response.status_code == 302
    with app.app_context():
        assert KnowledgeEntry.query.get(entry_id).source_issue_id is None
    assert "降低测量伪影" not in initialized_client.get(f"/issues/{issue_id}").get_data(as_text=True)
    assert "独立知识记录" in initialized_client.get(f"/knowledge/{entry_id}").get_data(as_text=True)
    initialized_client.post(
        f"/knowledge/{entry_id}/update",
        data={"title": "降低测量伪影", "content": "使用短地弹簧。", "issue_ref": f"#{issue_id} · 电源纹波异常"},
    )
    with app.app_context():
        assert KnowledgeEntry.query.get(entry_id).source_issue_id == issue_id


def test_knowledge_issue_picker_is_bounded_and_validated(app, initialized_client):
    from app.models import KnowledgeEntry

    for number in range(25):
        initialized_client.post("/issues", data={"title": f"实践问题 {number:02}"})
    options = initialized_client.get("/knowledge/issue-options?q=实践问题").get_json()["options"]
    assert len(options) == 20
    assert all(option.startswith("#") for option in options)
    assert initialized_client.get("/knowledge/issue-options?q=%23" + "9" * 40).get_json()["options"] == []
    response = initialized_client.post(
        "/knowledge", data={"title": "无效关联", "content": "正文", "issue_ref": "随便输入的问题"}
    )
    assert response.status_code == 302
    with app.app_context():
        assert KnowledgeEntry.query.filter_by(title="无效关联").count() == 0


def test_knowledge_from_issue_cell_keeps_its_original_issue(app, initialized_client):
    from app.models import KnowledgeEntry

    first = initialized_client.post("/issues", data={"title": "原始问题"})
    second = initialized_client.post("/issues", data={"title": "其他问题"})
    first_id = int(first.headers["Location"].rstrip("/").split("/")[-1])
    second_id = int(second.headers["Location"].rstrip("/").split("/")[-1])
    initialized_client.post(
        f"/issues/{first_id}/cells", data={"kind": "知识积累", "title": "来源固定", "content": "实践总结"}
    )
    with app.app_context():
        entry_id = KnowledgeEntry.query.filter_by(title="来源固定").one().id
    initialized_client.post(
        f"/knowledge/{entry_id}/update",
        data={"title": "来源固定", "content": "实践总结", "issue_ref": f"#{second_id} · 其他问题"},
    )
    with app.app_context():
        assert KnowledgeEntry.query.get(entry_id).source_issue_id == first_id
