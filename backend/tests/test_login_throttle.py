"""
Rate-Limit der Anmeldung (F-005, Plan §11).

Der Backoff selbst ist eine reine Funktion und wird ohne Redis und ohne DB
geprüft. Die Redis-Anbindung läuft gegen einen Fake-Client: ein echter Server
würde die Aussagen über Zeitfenster nur langsamer machen, nicht sicherer.
"""

from types import SimpleNamespace

import pytest

from core import login_throttle as lt


class _FakePipeline:
    def __init__(self, store):
        self._store = store
        self._ops = []

    def incr(self, key):
        self._ops.append(("incr", key))
        return self

    def expire(self, key, seconds):
        self._ops.append(("expire", key, seconds))
        return self

    def execute(self):
        results = []
        for op in self._ops:
            if op[0] == "incr":
                self._store.values[op[1]] = int(self._store.values.get(op[1], 0)) + 1
                results.append(self._store.values[op[1]])
            else:
                self._store.ttls[op[1]] = op[2]
                results.append(True)
        self._ops = []
        return results


class _FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    def get(self, key):
        return self.values.get(key)

    def pipeline(self):
        return _FakePipeline(self)

    def setex(self, key, seconds, value):
        self.values[key] = value
        self.ttls[key] = seconds

    def ttl(self, key):
        return self.ttls.get(key, -2)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.ttls.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch):
    client = _FakeRedis()
    monkeypatch.setattr(lt, "_redis", lambda: client)
    return client


@pytest.fixture
def no_redis(monkeypatch):
    monkeypatch.setattr(lt, "_redis", lambda: None)


# --- Backoff (reine Rechnung) ------------------------------------------------

@pytest.mark.parametrize("failures", [0, 1, 3, 5])
def test_first_attempts_are_free(failures):
    assert lt.lock_seconds_for(failures) == 0


def test_backoff_doubles_from_the_first_lock():
    assert lt.lock_seconds_for(6) == 60
    assert lt.lock_seconds_for(7) == 120
    assert lt.lock_seconds_for(8) == 240


def test_backoff_is_capped():
    # Ohne Deckel wäre die Sperre nach ~20 Fehlversuchen praktisch endgültig —
    # ein Denial-of-Service gegen ein Konto, das der Angreifer nur kennen muss.
    assert lt.lock_seconds_for(100) == lt.MAX_LOCK_SECONDS


# --- Redis-Zähler ------------------------------------------------------------

def test_failures_are_counted_per_username_and_ip(fake_redis):
    for expected in (1, 2, 3):
        assert lt.register_failure("alice", "10.0.0.1") == expected
    # Andere IP, gleicher Name: eigener Zähler.
    assert lt.register_failure("alice", "10.0.0.2") == 1


def test_db_counter_wins_when_it_is_higher(fake_redis):
    # Nach einem Redis-Neustart steht dort 0, die users-Zeile zählt weiter —
    # maßgeblich ist der höhere Wert, sonst wäre ein Redis-Flush ein Reset der Sperre.
    assert lt.register_failure("alice", "10.0.0.1", db_failed_count=9) == 9


def test_counter_gets_an_expiry(fake_redis):
    lt.register_failure("alice", "10.0.0.1")
    key = lt._key("alice", "10.0.0.1")
    assert fake_redis.ttls[key] == lt.FAILURE_WINDOW_SECONDS


def test_lock_is_readable_back(fake_redis):
    lt.set_lock("alice", "10.0.0.1", 120)
    assert lt.remaining_lock_seconds("alice", "10.0.0.1") == 120
    assert lt.remaining_lock_seconds("bob", "10.0.0.1") == 0


def test_successful_login_clears_counter_and_lock(fake_redis):
    lt.register_failure("alice", "10.0.0.1")
    lt.set_lock("alice", "10.0.0.1", 120)
    lt.clear_failures("alice", "10.0.0.1")
    assert lt.current_failures("alice", "10.0.0.1") == 0
    assert lt.remaining_lock_seconds("alice", "10.0.0.1") == 0


def test_username_case_does_not_open_a_second_bucket(fake_redis):
    lt.register_failure("Alice", "10.0.0.1")
    assert lt.current_failures("alice", "10.0.0.1") == 1


# --- Redis nicht erreichbar --------------------------------------------------

def test_without_redis_the_db_counter_still_counts(no_redis):
    assert lt.register_failure("alice", "10.0.0.1", db_failed_count=4) == 4
    assert lt.remaining_lock_seconds("alice", "10.0.0.1") == 0
    lt.clear_failures("alice", "10.0.0.1")  # darf nicht werfen


# --- Client-IP ---------------------------------------------------------------

def _request(headers, host="127.0.0.1"):
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_client_ip_prefers_the_first_forwarded_entry():
    req = _request({"x-forwarded-for": "203.0.113.7, 10.0.0.9"}, host="10.0.0.9")
    assert lt.client_ip_of(req) == "203.0.113.7"


def test_client_ip_falls_back_to_the_socket_address():
    assert lt.client_ip_of(_request({}, host="10.0.0.9")) == "10.0.0.9"


def test_client_ip_survives_a_missing_client():
    assert lt.client_ip_of(SimpleNamespace(headers={}, client=None)) == "unknown"
