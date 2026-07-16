"""用户认证 API 烟雾测试

测试注册和登录流程，覆盖有效凭证和无效凭证场景。
"""

from fastapi.testclient import TestClient

REGISTER_URL = "/api/user/register"
LOGIN_URL = "/api/user/login"


def _register_user(client: TestClient, username: str = "testuser") -> None:
    """辅助函数：注册测试用户"""
    resp = client.post(
        REGISTER_URL,
        json={"username": username, "password": "StrongPass1", "role": "student"},
    )
    assert resp.status_code == 200


def test_register_and_login_success(client: TestClient) -> None:
    """注册新用户并使用正确凭证登录 → 返回 200 + access_token"""
    _register_user(client)

    resp = client.post(
        LOGIN_URL, json={"username": "testuser", "password": "StrongPass1"}
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["code"] == 200
    assert data["message"] == "登录成功"

    token_data = data["data"]
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["user"]["username"] == "testuser"
    assert token_data["user"]["role"] == "student"


def test_login_invalid_password(client: TestClient) -> None:
    """错误密码 → 400"""
    _register_user(client, username="pwd_test")

    resp = client.post(
        LOGIN_URL, json={"username": "pwd_test", "password": "WrongPass1"}
    )
    assert resp.status_code == 400

    data = resp.json()
    assert "detail" in data


def test_login_nonexistent_user(client: TestClient) -> None:
    """不存在的用户名 → 400"""
    resp = client.post(
        LOGIN_URL,
        json={"username": "nobody", "password": "SomePass123"},
    )
    assert resp.status_code == 400

    data = resp.json()
    assert "detail" in data


def test_register_duplicate_username(client: TestClient) -> None:
    """重复注册用户名 → 400"""
    _register_user(client, username="dup_user")

    resp = client.post(
        REGISTER_URL,
        json={"username": "dup_user", "password": "AnotherPass1", "role": "student"},
    )
    assert resp.status_code == 400

    data = resp.json()
    assert "detail" in data
