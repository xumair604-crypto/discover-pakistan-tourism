"""Run with:  cd backend && python -m pytest -q"""
import json
import os
import sys

import pytest
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as backend  # noqa: E402

SITE = "https://xumair604-crypto.github.io"


@pytest.fixture
def app(tmp_path):
    application = backend.create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE": str(tmp_path / "test.sqlite3"),
        "SESSION_COOKIE_SECURE": False,
        "ALLOWED_ORIGINS": [SITE],
    })
    conn = backend.connect(application.config["DATABASE"])
    conn.execute("insert into admins (username, password_hash, created_at) values (?, ?, ?)",
                 ("latif", generate_password_hash("correct-horse-1"), backend.now_iso()))
    conn.commit()
    conn.close()
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username="latif", password="correct-horse-1"):
    res = client.post("/api/admin/login", json={"username": username, "password": password})
    return res, (res.get_json() or {}).get("csrf")


def booking(**extra):
    data = {"ref": "DP-ABC234", "source": "enquiry", "name": "Ali", "phone": "0300 1234567",
            "service": "Group tour", "destination": "Murree", "travel_date": "2026-12-20", "guests": "6 to 15"}
    data.update(extra)
    return data


# ---------------- Public API ----------------
def test_content_is_seeded_and_public(client):
    res = client.get("/api/content", headers={"Origin": SITE})
    body = res.get_json()
    assert res.status_code == 200
    assert res.headers["Access-Control-Allow-Origin"] == SITE
    assert [t["id"] for t in body["tours"]][:3] == ["murree", "galiyat", "hazara"]
    assert len(body["tours"]) == 11 and len(body["hotels"]) == 5 and len(body["venues"]) == 4 and len(body["offers"]) == 1
    assert isinstance(body["tours"][0]["plan"], list)


def test_other_origin_gets_no_cors_header(client):
    res = client.get("/api/content", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in res.headers


def test_booking_saved_with_text_plain_body(client):
    res = client.post("/api/bookings", data=json.dumps(booking()), content_type="text/plain;charset=UTF-8", headers={"Origin": SITE})
    assert res.status_code == 201 and res.get_json()["ref"] == "DP-ABC234"


def test_booking_from_other_website_rejected(client):
    res = client.post("/api/bookings", json=booking(), headers={"Origin": "https://evil.example"})
    assert res.status_code == 403


def test_booking_validation(client):
    assert client.post("/api/bookings", json=booking(name="")).status_code == 400
    assert client.post("/api/bookings", json=booking(name="x" * 121)).status_code == 400
    assert client.post("/api/bookings", json=booking(travel_date="2026-02-30")).status_code == 400
    assert client.post("/api/bookings", json=booking(travel_date="next week")).status_code == 400
    assert client.post("/api/bookings", data="not json", content_type="text/plain").status_code == 400


def test_duplicate_or_bad_ref_gets_new_ref(client):
    client.post("/api/bookings", json=booking())
    second = client.post("/api/bookings", json=booking()).get_json()["ref"]
    bad = client.post("/api/bookings", json=booking(ref="<script>")).get_json()["ref"]
    assert second != "DP-ABC234" and second.startswith("DP-") and bad.startswith("DP-")


def test_visitor_cannot_set_status_or_notes(client, app):
    client.post("/api/bookings", json=booking(status="confirmed", admin_notes="hack", quoted_rate="0"))
    row = backend.connect(app.config["DATABASE"]).execute("select status, admin_notes, quoted_rate from bookings").fetchone()
    assert tuple(row) == ("new", None, None)


def test_details_are_cleaned(client, app):
    details = {"places": ["Swat and Kalam", "Other: Chitral"], "meals": ["Buffet"], "evil": "<x>", "days": "5"}
    client.post("/api/bookings", json=booking(source="trip_builder", details=details))
    saved = json.loads(backend.connect(app.config["DATABASE"]).execute("select details from bookings").fetchone()[0])
    assert saved == {"places": ["Swat and Kalam", "Other: Chitral"], "meals": ["Buffet"], "days": "5"}


def test_honeypot_stores_nothing(client, app):
    res = client.post("/api/bookings", json=booking(website="spam.example"))
    assert res.status_code == 201
    assert backend.connect(app.config["DATABASE"]).execute("select count(*) from bookings").fetchone()[0] == 0


def test_booking_rate_limit(app):
    app.config["BOOKINGS_PER_IP_PER_HOUR"] = 3
    client = app.test_client()
    codes = [client.post("/api/bookings", json=booking(ref=f"DP-RATE{i}A")).status_code for i in range(4)]
    assert codes == [201, 201, 201, 429]


def test_public_cannot_read_bookings(client):
    client.post("/api/bookings", json=booking())
    assert client.get("/api/admin/bookings").status_code == 401
    assert client.get("/api/admin/bookings.csv").status_code == 401
    assert client.patch("/api/admin/bookings/1", json={"status": "cancelled"}).status_code == 401


# ---------------- Owner login ----------------
def test_login_wrong_password(client):
    res, _ = login(client, password="wrong")
    assert res.status_code == 401


def test_login_lockout(app):
    app.config["LOGIN_FAILURES_PER_15_MIN"] = 3
    client = app.test_client()
    codes = [login(client, password="nope")[0].status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]


def test_changes_need_csrf_token(client):
    client.post("/api/bookings", json=booking())
    _, csrf = login(client)
    assert client.patch("/api/admin/bookings/1", json={"status": "quoted"}).status_code == 403
    assert client.patch("/api/admin/bookings/1", json={"status": "quoted"}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.patch("/api/admin/bookings/1", json={"status": "quoted"}, headers={"X-CSRF-Token": csrf}).status_code == 200


def test_owner_manages_bookings(client):
    client.post("/api/bookings", json=booking())
    _, csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    rows = client.get("/api/admin/bookings").get_json()
    assert len(rows) == 1 and rows[0]["ref"] == "DP-ABC234"
    res = client.patch("/api/admin/bookings/1", json={"status": "quoted", "quoted_rate": "PKR 45,000", "admin_notes": "Called"}, headers=h)
    assert res.get_json()["status"] == "quoted" and res.get_json()["quoted_rate"] == "PKR 45,000"
    assert client.patch("/api/admin/bookings/1", json={"status": "bogus"}, headers=h).status_code == 400
    csv_text = client.get("/api/admin/bookings.csv").get_data(as_text=True)
    assert "DP-ABC234" in csv_text and "PKR 45,000" in csv_text
    assert client.delete("/api/admin/bookings/1", headers=h).status_code == 200
    assert client.get("/api/admin/bookings").get_json() == []


def test_csv_blocks_formula_injection(client):
    client.post("/api/bookings", json=booking(name="=HYPERLINK(\"http://x\")"))
    login(client)
    assert "'=HYPERLINK" in client.get("/api/admin/bookings.csv").get_data(as_text=True)


def test_owner_manages_content(client):
    _, csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    new = {"id": "chitral-kalash", "title": "Chitral and Kalash", "region": "Gilgit-Baltistan", "length": "long",
           "plan": [["Day 1", "Drive to Chitral"]], "incl": ["Car"], "excl": [], "sort": 95}
    assert client.post("/api/admin/tours", json=new, headers=h).status_code == 201
    assert client.post("/api/admin/tours", json=new, headers=h).status_code == 400  # duplicate id
    assert client.post("/api/admin/tours", json={**new, "id": "Bad ID"}, headers=h).status_code == 400
    assert client.post("/api/admin/tours", json={**new, "id": "x-img", "img": "javascript:alert(1)"}, headers=h).status_code == 400
    assert client.patch("/api/admin/tours/lahore", json={"published": False}, headers=h).status_code == 200
    ids = [t["id"] for t in client.get("/api/content").get_json()["tours"]]
    assert "lahore" not in ids and "chitral-kalash" in ids
    assert len(client.get("/api/admin/tours").get_json()) == 12  # owners still see hidden tours
    hotel = client.post("/api/admin/hotels", json={"name": "Pearl Continental Bhurban"}, headers=h).get_json()
    assert hotel["icon"] == "buildings" and hotel["published"] is True
    assert client.delete(f"/api/admin/hotels/{hotel['id']}", headers=h).status_code == 200
    assert client.post("/api/admin/offers", json={"body": "no title"}, headers=h).status_code == 400
    assert client.get("/api/admin/admins").status_code == 404  # no such content type


def test_change_password_and_logout(client):
    _, csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    assert client.post("/api/admin/password", json={"current": "wrong", "new": "another-pass-2"}, headers=h).status_code == 400
    assert client.post("/api/admin/password", json={"current": "correct-horse-1", "new": "short"}, headers=h).status_code == 400
    assert client.post("/api/admin/password", json={"current": "correct-horse-1", "new": "another-pass-2"}, headers=h).status_code == 200
    assert client.post("/api/admin/logout", headers=h).status_code == 200
    assert client.get("/api/admin/me").status_code == 401
    assert login(client, password="another-pass-2")[0].status_code == 200


def test_admin_page_served_with_safe_headers(client):
    res = client.get("/admin")
    assert res.status_code == 200 and b"Owner sign in" in res.data
    assert res.headers["X-Frame-Options"] == "DENY" and res.headers["Cache-Control"] == "no-store"


def test_cookie_flags(client):
    res, _ = login(client)
    cookie = res.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
