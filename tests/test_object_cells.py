from app.models import ObjectCell, PCB, Project


def test_project_can_bind_pcbs_and_project_and_pcb_accept_cells(app, initialized_client):
    initialized_client.post(
        "/pcbs",
        data={"model": "CTRL-A", "serial": "CTRL-A-001", "revision": "V1.0"},
    )
    initialized_client.post(
        "/pcbs",
        data={"model": "CTRL-A", "serial": "CTRL-A-002", "revision": "V1.1"},
    )
    with app.app_context():
        pcb_ids = [row.id for row in PCB.query.order_by(PCB.id).all()]

    response = initialized_client.post(
        "/projects",
        data={"name": "CTRL-A 联调", "objective": "完成两块样板联调"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        project_id = Project.query.filter_by(name="CTRL-A 联调").one().id
    assert response.headers["Location"].endswith(f"/projects/{project_id}")

    response = initialized_client.post(
        f"/projects/{project_id}/pcbs",
        data={"pcb_ids": [str(pcb_ids[0]), str(pcb_ids[1])]},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "CTRL-A-001" in response.get_data(as_text=True)
    assert "CTRL-A-002" in response.get_data(as_text=True)
    project_page = response.get_data(as_text=True)
    assert project_page.index('class="composer object-composer"') < project_page.index('class="chat-timeline"')

    response = initialized_client.post(
        f"/projects/{project_id}/cells",
        data={"kind": "阶段结论", "content": "两块样板已完成基础功能验证"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "两块样板已完成基础功能验证" in response.get_data(as_text=True)

    response = initialized_client.post(
        f"/pcbs/{pcb_ids[0]}/cells",
        data={"kind": "测试记录", "content": "第一块板卡的 3V3 纹波正常"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "第一块板卡的 3V3 纹波正常" in response.get_data(as_text=True)
    pcb_page = response.get_data(as_text=True)
    assert pcb_page.index('class="composer object-composer"') < pcb_page.index('class="timeline"')

    with app.app_context():
        project = Project.query.get(project_id)
        assert {pcb.id for pcb in project.pcbs} == set(pcb_ids)
        project_cell = ObjectCell.query.filter_by(project_id=project_id).one()
        pcb_cell = ObjectCell.query.filter_by(pcb_id=pcb_ids[0]).one()
        assert project_cell.pcb_id is None
        assert pcb_cell.project_id is None


def test_object_cell_requires_exactly_one_owner(app, initialized_client):
    initialized_client.post("/projects", data={"name": "空项目"})
    with app.app_context():
        project_id = Project.query.filter_by(name="空项目").one().id

    response = initialized_client.post(
        f"/projects/{project_id}/cells",
        data={"kind": "普通记录", "content": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        assert ObjectCell.query.count() == 0


def test_project_and_pcb_cells_can_be_trashed_and_restored(app, initialized_client):
    initialized_client.post("/projects", data={"name": "项目 A"})
    initialized_client.post("/pcbs", data={"serial": "SER-1", "model": "型号 A"})
    with app.app_context():
        project_id = Project.query.filter_by(name="项目 A").one().id
        pcb_id = PCB.query.filter_by(serial="SER-1").one().id
    initialized_client.post(f"/projects/{project_id}/cells", data={"content": "项目专属进展 123"})
    initialized_client.post(f"/pcbs/{pcb_id}/cells", data={"content": "板卡专属测量 456"})
    with app.app_context():
        project_cell_id = ObjectCell.query.filter_by(project_id=project_id).one().id
        pcb_cell_id = ObjectCell.query.filter_by(pcb_id=pcb_id).one().id
    assert f"/projects/{project_id}/cells/{project_cell_id}/trash" in initialized_client.get(f"/projects/{project_id}").get_data(as_text=True)
    assert f"/pcbs/{pcb_id}/cells/{pcb_cell_id}/trash" in initialized_client.get(f"/pcbs/{pcb_id}").get_data(as_text=True)
    assert initialized_client.post(f"/pcbs/{pcb_id}/cells/{project_cell_id}/trash").status_code == 404
    assert initialized_client.post(f"/projects/{project_id}/cells/{project_cell_id}/trash").status_code == 302
    assert initialized_client.post(f"/pcbs/{pcb_id}/cells/{pcb_cell_id}/trash").status_code == 302
    assert "项目专属进展 123" not in initialized_client.get(f"/projects/{project_id}").get_data(as_text=True)
    assert "板卡专属测量 456" not in initialized_client.get(f"/pcbs/{pcb_id}").get_data(as_text=True)
    trash = initialized_client.get("/trash").get_data(as_text=True)
    assert "项目专属进展 123" in trash and "板卡专属测量 456" in trash
    initialized_client.post(f"/trash/restore/object_cell/{project_cell_id}")
    initialized_client.post(f"/trash/restore/object_cell/{pcb_cell_id}")
    assert "项目专属进展 123" in initialized_client.get(f"/projects/{project_id}").get_data(as_text=True)
    assert "板卡专属测量 456" in initialized_client.get(f"/pcbs/{pcb_id}").get_data(as_text=True)
