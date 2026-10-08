import copy

from app import tracking


def by_name(acts):
    return {a["name"]: a for a in acts}


def test_status_classification(board):
    acts = by_name(tracking.build_activities(board))
    assert acts["Diseñar base de datos"]["status"] == "completada"
    assert acts["API de usuarios"]["status"] == "retrasada"
    assert acts["Pantalla de login"]["status"] == "pendiente"
    assert acts["Integración pagos"]["status"] == "bloqueada"
    assert acts["API de usuarios"]["priority"] == "Alta"
    assert acts["API de usuarios"]["responsables"] == ["Luis Mora"]


def test_risk_and_dependencies(board):
    acts = by_name(tracking.build_activities(board))
    login = acts["Pantalla de login"]
    assert login["at_risk"] and any("vence" in r for r in login["risk_reasons"])
    assert login["depends_on"] == ["C2"]
    # C2 retrasada impacta a C3 y, transitivamente, a C4
    assert set(acts["API de usuarios"]["blocks"]) == {"C3", "C4"}
    assert not acts["Despliegue"]["at_risk"]


def test_summary(board):
    s = tracking.summarize(tracking.build_activities(board))
    assert s["total"] == 5
    assert s["counts"] == {"pendiente": 2, "en_ejecucion": 0, "completada": 1, "retrasada": 1, "bloqueada": 1}
    assert s["progress_completed"] == 20.0
    assert s["progress_weighted"] == 30.0  # (1 + 0.5 + 0 + 0 + 0) / 5


def test_change_detection(board):
    old = tracking.snapshot(board)
    new_board = copy.deepcopy(board)
    new_board["cards"][2]["due"] = "2030-01-01T00:00:00Z"
    new_board["cards"][2]["idMembers"] = ["M2"]
    new_board["cards"].pop(3)
    changes = tracking.diff_snapshots(old, tracking.snapshot(new_board))
    fields = {(c["card_name"], c["field"]) for c in changes}
    assert ("Pantalla de login", "fecha_limite") in fields
    assert ("Pantalla de login", "responsables") in fields
    assert ("Despliegue", "tarjeta") in fields


def test_phase_board_infers_status_from_dates(board):
    from tests.conftest import iso
    board["lists"] = [{"id": "F1", "name": "Fase 1: Diseño"}]
    for c in board["cards"]:
        c["idList"] = "F1"
        c["labels"], c["idLabels"] = [], []
    board["cards"][1].update(start=iso(-3), due=iso(4), dueComplete=False, checklists=[])   # en curso
    board["cards"][2].update(start=iso(2), due=iso(9))                                       # aún no inicia
    board["cards"][3].update(start=iso(-9), due=iso(-1))                                     # vencida
    acts = {a["id"]: a for a in tracking.build_activities(board)}
    assert acts["C1"]["status"] == "completada"
    assert acts["C2"]["status"] == "en_ejecucion" and acts["C2"]["progress"] == 0.5
    assert acts["C3"]["status"] == "pendiente"
    assert acts["C4"]["status"] == "retrasada"
