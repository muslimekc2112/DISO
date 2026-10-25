"""Shared by the account, sharing and friends tests: a pretend Supabase in place of the real one (fixture `cloud`),
and small helpers."""
import json
import os

import pytest
from fake_supabase import FakeSupabase

from app import account


@pytest.fixture
def cloud(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(account, "_call", fake)
    monkeypatch.setattr(account, "_raw", fake.raw)
    return fake


def ready(cloud, username="ali", first="Ali", last="Yılmaz", address=None, password="gizli123"):
    """An account made and confirmed (signed in on this computer)."""
    address = address or f"{username}@gmail.com"
    account.sign_up(first, last, username, address, password)
    return account.verify_code(cloud.last_code(address))


def write(folder, name, data):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        json.dump(data, f)


def read(folder, name):
    with open(os.path.join(folder, name), encoding="utf-8") as f:
        return json.load(f)
