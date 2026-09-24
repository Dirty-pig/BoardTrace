from datetime import timedelta

from app.extensions import db
from app.models import ObjectCell, PCB, utcnow


def test_pcb_list_searches_serial_only(app, initialized_client):
    with app.app_context():
        db.session.add_all([
            PCB(model="MATCH-MODEL", revision="V1", serial="PCB-001"),
            PCB(model="OTHER", revision="MATCH-REVISION", serial="PCB-002"),
            PCB(model="OTHER", revision="V2", serial="MATCH-003"),
        ])
        db.session.commit()

    page = initialized_client.get("/pcbs?q=MATCH").get_data(as_text=True)
    listing = page.split('<section class="panel table-panel">', 1)[1].split("</section>", 1)[0]
    assert "仅按 PCB 序列号搜索" in page
    assert "MATCH-003" in listing
    assert "PCB-001" not in listing
    assert "PCB-002" not in listing
    assert 'data-pcb-cascade' not in page


def test_pcb_timeline_stays_paginated(app, initialized_client):
    with app.app_context():
        pcb = PCB(model="CTRL-A", revision="V1", serial="A-001")
        db.session.add(pcb)
        db.session.flush()
        pcb_id = pcb.id
        base = utcnow()
        db.session.add_all(
            ObjectCell(pcb_id=pcb_id, content_md=f"line-{number:02d}", rendered_html=f"line-{number:02d}", created_at=base + timedelta(minutes=number))
            for number in range(45)
        )
        db.session.commit()

    first = initialized_client.get(f"/pcbs/{pcb_id}").get_data(as_text=True)
    third = initialized_client.get(f"/pcbs/{pcb_id}?page=3").get_data(as_text=True)
    assert "line-44" in first and "line-00" not in first
    assert "line-00" in third and "line-44" not in third
    assert "加载更早记录" in first
    assert "加载更早记录" not in third
