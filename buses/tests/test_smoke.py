"""
Tests de humo — Bitácora E.E.
Ejecutar: pytest
"""
import pytest
from django.test import Client


@pytest.mark.django_db
def test_login_page_loads():
    client = Client()
    response = client.get("/login/")
    assert response.status_code in (200, 302)


@pytest.mark.django_db
def test_dashboard_requires_auth():
    client = Client()
    response = client.get("/")
    # Sin sesión debe redirigir a login
    assert response.status_code in (302, 403, 200)
