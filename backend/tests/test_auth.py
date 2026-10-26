from tests.conftest import add_member, login, signup


def test_signup_then_login_works(client):
    signup(client, "Team A", "Admin@A.com")
    headers = login(client, "admin@a.com")  # email is stored lowercase
    me = client.get("/auth/me", headers=headers).json()
    assert me["email"] == "admin@a.com"
    assert me["role"] == "admin"


def test_wrong_password_fails(client):
    signup(client, "Team A", "admin@a.com")
    response = client.post("/auth/login", data={"username": "admin@a.com", "password": "not-the-password"})
    assert response.status_code == 401


def test_unknown_email_gets_same_error_as_wrong_password(client):
    response = client.post("/auth/login", data={"username": "nobody@a.com", "password": "whatever123"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Wrong email or password"


def test_duplicate_email_rejected(client):
    signup(client, "Team A", "admin@a.com")
    response = client.post("/auth/signup", json={"team_name": "Other", "email": "admin@a.com", "password": "password123"})
    assert response.status_code == 400


def test_requests_without_token_are_rejected(client):
    assert client.get("/projects").status_code == 401
    assert client.get("/projects", headers={"Authorization": "Bearer forged.token.value"}).status_code == 401


def test_password_is_not_stored_in_plain_text(client):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import User

    signup(client, "Team A", "admin@a.com", password="password123")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@a.com"))
        assert "password123" not in user.password_hash


def test_only_admin_can_add_members(client, admin):
    member = add_member(client, admin, "member@a.com")
    response = client.post("/team/members", json={"email": "x@a.com", "password": "password123"}, headers=member)
    assert response.status_code == 403
    emails = [m["email"] for m in client.get("/team/members", headers=member).json()]
    assert emails == ["admin@a.com", "member@a.com"]
