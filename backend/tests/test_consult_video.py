"""Step 5: video calls. Only set-up messages pass through the backend (never media). A call needs a doctor-accepted case, only the two parties can use it, the
other side sees what was sent but not their own echo, ending wipes the set-up data, and everything is audited."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, ConsultCase, ConsultSignal
from devtools import demo_data as dd
from tests.test_consult import DOCTOR2, add_doctor, ask
from tests.test_consult_chat import accepted_case, doctor_login
from tests.test_messages import env, login, signup  # noqa: F401


def person_call(c, case_id, kind, payload=None):
    return c.post(f"/api/consults/{case_id}/call", json={"kind": kind, "payload": payload})


def doctor_call(c, case_id, kind, payload=None):
    return c.post(f"/api/doctor/cases/{case_id}/call", json={"kind": kind, "payload": payload})


def test_a_call_cannot_start_before_a_doctor_has_accepted(env):
    with TestClient(app) as c:
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        case_id = ask(c).json()["id"]
        assert person_call(c, case_id, "request").status_code == 409


def test_the_other_side_sees_the_request_but_not_their_own_echo(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        assert doctor_call(c, case_id, "request").status_code == 201
        assert c.get(f"/api/doctor/cases/{case_id}/call").json() == []                      # the doctor does not get their own request back
        login(c, dd.NORMAL.signup)
        seen = c.get(f"/api/consults/{case_id}/call").json()
        assert [(s["sender_role"], s["kind"]) for s in seen] == [("doctor", "request")]


def test_a_full_set_up_exchange_passes_through_and_is_audited(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        doctor_call(c, case_id, "request")
        login(c, dd.NORMAL.signup)
        person_call(c, case_id, "accept")
        doctor_login(c)
        doctor_call(c, case_id, "offer", {"sdp": "v=0 offer", "type": "offer"})
        login(c, dd.NORMAL.signup)
        got = c.get(f"/api/consults/{case_id}/call?after=0").json()
        assert [s["kind"] for s in got] == ["request", "offer"] and got[1]["payload"]["sdp"] == "v=0 offer"
        person_call(c, case_id, "answer", {"sdp": "v=0 answer", "type": "answer"})
        person_call(c, case_id, "end")
    with env() as s:
        actions = [a.action for a in s.scalars(select(AuditLog))]
        assert {"video_request", "video_accept", "video_end"} <= set(actions)
        assert s.get(ConsultCase, case_id).video_used is True


def test_ending_a_call_wipes_the_set_up_data_but_keeps_the_end_event(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        doctor_call(c, case_id, "request")
        doctor_call(c, case_id, "offer", {"sdp": "x"})
        doctor_call(c, case_id, "ice", {"candidate": "candidate:1 1 udp 1 10.0.0.1 5000 typ host"})
        doctor_call(c, case_id, "end")
    with env() as s:
        left = s.scalars(select(ConsultSignal).where(ConsultSignal.case_id == case_id)).all()
        assert [x.kind for x in left] == ["end"]


def test_declining_wipes_the_set_up_data_too(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        doctor_call(c, case_id, "request")
        login(c, dd.NORMAL.signup)
        person_call(c, case_id, "decline")
    with env() as s:
        assert [x.kind for x in s.scalars(select(ConsultSignal).where(ConsultSignal.case_id == case_id))] == ["decline"]


def test_a_new_request_starts_clean(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        doctor_call(c, case_id, "request")
        doctor_call(c, case_id, "offer", {"sdp": "old"})
        doctor_call(c, case_id, "request")
    with env() as s:
        assert [x.kind for x in s.scalars(select(ConsultSignal).where(ConsultSignal.case_id == case_id))] == ["request"]


def test_nobody_else_can_use_a_case_call(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        doctor_call(c, case_id, "request")
        add_doctor(c, env, DOCTOR2)
        doctor_login(c, DOCTOR2)
        assert doctor_call(c, case_id, "accept").status_code == 404
        assert c.get(f"/api/doctor/cases/{case_id}/call").status_code == 404
        c.post("/api/auth/logout")
        signup(c, dd.HIGH.signup, dd.HIGH.answers)
        assert person_call(c, case_id, "accept").status_code == 404
        assert c.get(f"/api/consults/{case_id}/call").status_code == 404


def test_closing_the_case_removes_any_set_up_data_and_blocks_new_calls(env):
    from tests.test_consult_close import NOTE

    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        doctor_call(c, case_id, "request")
        doctor_call(c, case_id, "offer", {"sdp": "x"})
        assert c.post(f"/api/doctor/cases/{case_id}/close", json={**NOTE, "mode": "both"}).status_code == 200
        assert doctor_call(c, case_id, "request").status_code == 409
        login(c, dd.NORMAL.signup)
        assert person_call(c, case_id, "request").status_code == 409
    with env() as s:
        assert s.scalars(select(ConsultSignal).where(ConsultSignal.case_id == case_id)).all() == []


def test_oversized_payloads_and_unknown_kinds_are_refused(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        assert doctor_call(c, case_id, "offer", {"sdp": "x" * 25000}).status_code == 422
        assert doctor_call(c, case_id, "hack").status_code == 422


def test_the_ice_servers_are_available_to_a_signed_in_user_only(env):
    with TestClient(app) as c:
        assert c.get("/api/consults/ice").status_code == 401
        signup(c, dd.NORMAL.signup, dd.NORMAL.answers)
        assert c.get("/api/consults/ice").json()["ice_servers"][0]["urls"].startswith("stun:")


def test_the_doctor_case_detail_says_whether_video_was_used(env):
    with TestClient(app) as c:
        case_id = accepted_case(c, env)
        assert c.get(f"/api/doctor/cases/{case_id}").json()["video_used"] is False
        doctor_call(c, case_id, "request")
        login(c, dd.NORMAL.signup)
        person_call(c, case_id, "accept")
        doctor_login(c)
        assert c.get(f"/api/doctor/cases/{case_id}").json()["video_used"] is True
