"""[담당: 장수민] 매핑 사전 API 테스트 — GET /mappings, DELETE /mappings/{id}, GET /mappings/conversions
(명세 v1.4 4.23). 실제 DB 필요."""
import pytest

from app.core.enums import ItemMappingSource
from app.models import ItemMapping
from app.services import mapping_service


@pytest.fixture
def mappings(db, admin):
    rows = [
        ItemMapping(material_code="LI2CO3", raw_name="Sodium (Na)", normalized_name="Na", source=ItemMappingSource.SEED),
        ItemMapping(material_code="LI2CO3", raw_name="Assay", normalized_name="순도", source=ItemMappingSource.SEED),
        ItemMapping(material_code="LI2CO3", raw_name="Titration excess HCl", normalized_name="순도",
                    source=ItemMappingSource.MANUAL, created_by=admin.id),
        ItemMapping(material_code="LIOH", raw_name="Sodium (Na)", normalized_name="Na", source=ItemMappingSource.SEED),
    ]
    db.add_all(rows)
    db.commit()
    return {r.raw_name + "/" + r.material_code: r.id for r in rows}


def listed(client, **params):
    r = client.get("/api/v1/mappings", params=params)
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ---- 조회 -------------------------------------------------------------------
def test_list_sorted_with_creator(auth_client, mappings):
    data = listed(auth_client)
    # 원자재 → 표준 항목명 → 협력사 항목명 순
    assert [(d["material_code"], d["normalized_name"], d["raw_name"]) for d in data] == [
        ("LI2CO3", "Na", "Sodium (Na)"),
        ("LI2CO3", "순도", "Assay"),
        ("LI2CO3", "순도", "Titration excess HCl"),
        ("LIOH", "Na", "Sodium (Na)"),
    ]
    manual = data[2]
    assert (manual["source"], manual["created_by"]) == ("manual", "관리자")
    assert (data[0]["source"], data[0]["created_by"]) == ("seed", None)
    assert manual["created_at"].endswith("+09:00")


def test_list_filters(auth_client, mappings):
    assert {d["material_code"] for d in listed(auth_client, material_code="LIOH")} == {"LIOH"}
    data = listed(auth_client, material_code="LI2CO3", normalized_name="순도")
    assert [d["raw_name"] for d in data] == ["Assay", "Titration excess HCl"]


def test_list_requires_login(client, mappings):
    assert client.get("/api/v1/mappings").status_code == 401


def test_manual_rename_appears_in_list(auth_client, db, mappings, user):
    mapping_service.upsert_manual(db, material_code="LI2CO3", raw_name="Calcium content", normalized_name="Ca",
                                  user_id=user.id)
    db.commit()
    row = next(d for d in listed(auth_client, normalized_name="Ca"))
    assert (row["raw_name"], row["source"], row["created_by"]) == ("Calcium content", "manual", "김사용")


# ---- 삭제 -------------------------------------------------------------------
def test_admin_deletes_mapping(auth_client, db, mappings, admin):
    target = mappings["Titration excess HCl/LI2CO3"]
    auth_client.login_as(admin)
    r = auth_client.delete(f"/api/v1/mappings/{target}")
    assert r.status_code == 200 and r.json()["data"] == {"id": target}
    assert mapping_service.lookup(db, "LI2CO3", "Titration excess HCl") is None   # 다음 문서부터 사전에 없음
    assert mapping_service.lookup(db, "LI2CO3", "Assay") == "순도"                 # 다른 매핑은 그대로
    assert len(listed(auth_client)) == 3


def test_user_cannot_delete(auth_client, db, mappings):
    target = mappings["Assay/LI2CO3"]
    r = auth_client.delete(f"/api/v1/mappings/{target}")
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    assert mapping_service.lookup(db, "LI2CO3", "Assay") == "순도"


def test_delete_not_found(auth_client, mappings, admin):
    auth_client.login_as(admin)
    r = auth_client.delete("/api/v1/mappings/99999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


# ---- 환산표 -----------------------------------------------------------------
def test_conversions(auth_client):
    r = auth_client.get("/api/v1/mappings/conversions")
    assert r.status_code == 200
    data = r.json()["data"]
    units = {(u["from"], u["to"]): u["factor"] for u in data["units"]}
    assert units[("%", "ppm")] == 10000 and units[("ppb", "ppm")] == 0.001
    oxides = {o["oxide"]: (o["element"], o["factor"]) for o in data["oxides"]}
    assert oxides["Na2O"] == ("Na", 0.7419) and oxides["Fe2O3"] == ("Fe", 0.6994) and oxides["CaO"] == ("Ca", 0.7147)


def test_conversions_require_login(client):
    assert client.get("/api/v1/mappings/conversions").status_code == 401
