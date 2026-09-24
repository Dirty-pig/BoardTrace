from types import SimpleNamespace

from app.display import EMPTY_PART, pcb_label


def test_pcb_label_orders_model_revision_serial():
    pcb = SimpleNamespace(model="M1533", revision="B", serial="00028")
    assert pcb_label(pcb) == "M1533 - B - 00028"
    assert pcb_label(pcb, include_model=False) == "B - 00028"


def test_pcb_label_preserves_three_space_missing_parts():
    pcb = SimpleNamespace(model="M1169", revision="", serial="00030")
    assert EMPTY_PART == "\u00a0" * 3
    assert pcb_label(pcb) == f"M1169 - {EMPTY_PART} - 00030"
    assert pcb_label(pcb, include_model=False) == f"{EMPTY_PART} - 00030"


def test_all_templates_compile_with_registered_filters(app):
    for name in app.jinja_env.list_templates():
        app.jinja_env.get_template(name)
