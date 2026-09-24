from datetime import timedelta

from app.extensions import db
from app.models import Issue, ObjectCell, PCB, WorkLog, utcnow


def test_pcb_options_are_scoped_and_bounded(app, initialized_client):
    with app.app_context():
        db.session.add_all(
            PCB(model="CTRL-A", revision=f"V{number:02d}", serial=f"A-{number:03d}")
            for number in range(42)
        )
        db.session.add(PCB(model="CTRL-B", revision="V01", serial="B-001"))
        db.session.add(PCB(model="CTRL-A", revision="OLD", serial="A-OLD", deleted_at=utcnow()))
        db.session.commit()

    models = initialized_client.get("/pcbs/options?field=model").get_json()
    assert models == {"options": ["CTRL-A", "CTRL-B"], "has_more": False}
    assert initialized_client.get("/pcbs/options?field=revision").get_json()["options"] == []
    revisions = initialized_client.get("/pcbs/options?field=revision&model=CTRL-A").get_json()
    assert len(revisions["options"]) == 30
    assert revisions["has_more"] is True
    assert "OLD" not in revisions["options"]
    assert initialized_client.get("/pcbs/options?field=revision&model=CTRL-A&q=V40").get_json()["options"] == ["V40"]
    serials = initialized_client.get("/pcbs/options?field=serial&model=CTRL-A&revision=V40").get_json()
    assert serials == {"options": ["A-040"], "has_more": False}
    assert initialized_client.get("/pcbs/options?field=serial&model=CTRL-B&revision=V40").get_json()["options"] == []
    assert initialized_client.get("/pcbs/options?field=unknown").status_code == 400

    page = initialized_client.get("/pcbs?model=CTRL-A&revision=V40&serial=A-040").get_data(as_text=True)
    assert page.index("板卡型号</th>") < page.index("版本号</th>") < page.index("PCB 序列号</th>")
    assert "A-040</td>" in page
    assert "A-041</td>" not in page


def test_pcb_timeline_uses_bounded_pages(app, initialized_client):
    with app.app_context():
        pcb = PCB(model="CTRL-A", revision="V1", serial="A-001")
        db.session.add(pcb)
        db.session.flush()
        pcb_id = pcb.id
        base = utcnow()
        db.session.add_all(
            ObjectCell(pcb_id=pcb_id, kind="普通记录", content_md=f"line-{number:02d}", rendered_html=f"line-{number:02d}", created_at=base + timedelta(minutes=number))
            for number in range(45)
        )
        db.session.add(Issue(pcb_id=pcb_id, title="问题记录", created_at=base + timedelta(minutes=45)))
        db.session.add(WorkLog(pcb_id=pcb_id, title="工作记录", minutes=25, created_at=base + timedelta(minutes=46)))
        db.session.commit()

    first = initialized_client.get(f"/pcbs/{pcb_id}").get_data(as_text=True)
    third = initialized_client.get(f"/pcbs/{pcb_id}?page=3").get_data(as_text=True)
    assert "line-44" in first and "line-00" not in first
    assert "line-00" in third and "line-44" not in third
    assert "25m" in first
    assert "加载更早记录" in first
    assert "加载更早记录" not in third
