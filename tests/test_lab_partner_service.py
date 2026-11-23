"""The lab partner scheduling service, alone and driven by the app's real HttpLabBackend / LabTools."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.tools.lab_backend import HttpLabBackend, SlotTaken
from app.tools.lab_tools import LabTools
from services.lab_partner.app import create_app

KEY = "test-partner-key"
FUTURE = date.today() + timedelta(days=5)


@pytest.fixture()
def partner(tmp_path):
    app = create_app(api_key=KEY, db_path=str(tmp_path / "partner.db"), packages_path="data/lab_packages.json")
    with TestClient(app) as c:
        yield c


H = {"Authorization": f"Bearer {KEY}"}


def _book(c, key="k1", slot="09:00 AM", pkg="LP_002", member="M1", day=FUTURE):
    return c.post("/bookings", headers={**H, "Idempotency-Key": key},
                  json={"package_id": pkg, "member_id": member, "date": day.isoformat(), "slot": slot})


# ------------------------------------------------------------------ the service on its own
def test_requires_a_key_to_start_and_a_token_to_call(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(api_key="", db_path=":memory:", packages_path="data/lab_packages.json")
    app = create_app(api_key=KEY, db_path=":memory:", packages_path="data/lab_packages.json")
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200                      # health needs no auth
        assert c.get("/slots", params={"package_id": "LP_002", "date": FUTURE.isoformat()}).status_code == 401
        assert c.get("/slots", params={"package_id": "LP_002", "date": FUTURE.isoformat()},
                     headers={"Authorization": "Bearer nope"}).status_code == 401
        assert c.post("/bookings", json={}).status_code == 401


def test_slots_follow_each_packages_window_and_shrink_when_booked(partner):
    fasting = partner.get("/slots", params={"package_id": "LP_001", "date": FUTURE.isoformat()}, headers=H).json()
    regular = partner.get("/slots", params={"package_id": "LP_002", "date": FUTURE.isoformat()}, headers=H).json()
    assert fasting["slots"][0] == "07:00 AM" and regular["slots"][0] == "09:00 AM"
    assert _book(partner).status_code == 201
    after = partner.get("/slots", params={"package_id": "LP_002", "date": FUTURE.isoformat()}, headers=H).json()
    assert "09:00 AM" not in after["slots"] and len(after["slots"]) == len(regular["slots"]) - 1
    assert partner.get("/slots", params={"package_id": "NOPE", "date": FUTURE.isoformat()}, headers=H).status_code == 404
    past = date.today() - timedelta(days=1)
    assert partner.get("/slots", params={"package_id": "LP_002", "date": past.isoformat()}, headers=H).json()["slots"] == []


def test_double_booking_is_a_409_and_cancel_frees_the_slot(partner):
    first = _book(partner, key="a")
    assert first.status_code == 201
    assert _book(partner, key="b", member="M2").status_code == 409
    ref = first.json()["booking_ref"]
    assert partner.delete(f"/bookings/{ref}", headers=H).status_code == 204
    assert partner.delete(f"/bookings/{ref}", headers=H).status_code == 204     # cancelling twice is fine
    assert partner.delete("/bookings/LP-NOPE", headers=H).status_code == 404
    assert _book(partner, key="c", member="M2").status_code == 201               # the slot is free again


def test_idempotency_a_retry_returns_the_same_booking_never_a_second(partner):
    a, b = _book(partner, key="same"), _book(partner, key="same")
    assert a.status_code == 201 and b.status_code in (200, 201)
    assert a.json()["booking_ref"] == b.json()["booking_ref"]
    assert len(partner.get("/bookings", headers=H).json()) == 1
    clash = _book(partner, key="same", slot="09:30 AM")                          # same key, different request
    assert clash.status_code == 422


def test_invalid_requests_are_rejected(partner):
    assert _book(partner, slot="03:00 AM").status_code == 422                    # slot outside the window
    assert _book(partner, slot="09:00 AM", pkg="LP_001").status_code == 422      # fasting package, regular slot
    assert _book(partner, pkg="NOPE").status_code == 404
    assert _book(partner, day=date.today() - timedelta(days=1)).status_code == 422
    assert partner.post("/bookings", headers=H, json={"package_id": "LP_002", "member_id": "M", "date": FUTURE.isoformat(),
                                                      "slot": "09:00 AM"}).status_code == 422   # no Idempotency-Key


def test_concurrent_requests_for_one_slot_produce_exactly_one_winner(partner):
    def go(i):
        return _book(partner, key=f"race-{i}", member=f"M{i}").status_code
    with ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(ex.map(go, range(8)))
    assert codes.count(201) == 1 and codes.count(409) == 7


def test_bookings_survive_a_restart_of_the_service(tmp_path):
    db = str(tmp_path / "p.db")
    with TestClient(create_app(api_key=KEY, db_path=db, packages_path="data/lab_packages.json")) as c:
        assert _book(c, key="persist").status_code == 201
    with TestClient(create_app(api_key=KEY, db_path=db, packages_path="data/lab_packages.json")) as c2:
        assert _book(c2, key="other", member="M2").status_code == 409            # still taken after the restart
        assert _book(c2, key="persist").json()["booking_ref"].startswith("LP-")  # and the key is still remembered


# ------------------------------------------------------------------ the app's real adapter against the service
class _AsHttp:
    """Lets the app's HttpLabBackend (which expects a requests-style session) talk to the in-process service."""

    def __init__(self, client, base):
        self.c, self.base = client, base

    def request(self, method, url, timeout=None, headers=None, params=None, json=None):
        return self.c.request(method, url[len(self.base):], headers=headers, params=params, json=json)


def _backend(partner):
    base = "http://partner.test"
    return HttpLabBackend(base, KEY, 2.0, session=_AsHttp(partner, base))


def test_adapter_books_cancels_and_sees_conflicts_against_the_real_service(partner):
    b = _backend(partner)
    ref = b.reserve(package_id="LP_002", member_id="M1", day=FUTURE, slot="09:00 AM", idempotency_key="x").booking_ref
    assert ref.startswith("LP-")
    with pytest.raises(SlotTaken):
        b.reserve(package_id="LP_002", member_id="M2", day=FUTURE, slot="09:00 AM", idempotency_key="y")
    assert "09:00 AM" not in b.free_slots("LP_002", FUTURE, [])
    b.release(ref)
    assert "09:00 AM" in b.free_slots("LP_002", FUTURE, [])


def test_labtools_end_to_end_two_app_instances_cannot_double_book_one_slot(partner):
    """Two app processes (separate LabTools, no shared memory) share only the partner: the partner is the authority."""
    app1, app2 = LabTools(backend=_backend(partner)), LabTools(backend=_backend(partner))
    pkg = app1.lab_packages[1].package_id
    r1 = app1.book_test(pkg, "MEM_1", "09:00 AM", FUTURE)
    r2 = app2.book_test(pkg, "MEM_2", "09:00 AM", FUTURE)
    assert r1.status == "booking_confirmed"
    assert r2.status == "booking_failed" and "taken" in r2.message
    assert "09:00 AM" not in app2.check_slots(pkg, FUTURE).slots              # app2 sees the partner's truth
    assert app1.cancel_booking(r1.booking_id, "MEM_1").status == "cancelled"
    assert app2.book_test(pkg, "MEM_2", "09:00 AM", FUTURE).status == "booking_confirmed"
