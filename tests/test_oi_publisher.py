from futuresbot.oi_publisher import read_oi_series, record_oi_snapshots


class FakeRedis:
    """Minimal in-memory stand-in for the few sorted-set ops we use."""

    def __init__(self):
        self.z = {}  # key -> {member: score}

    def zadd(self, key, mapping):
        self.z.setdefault(key, {}).update(mapping)

    def zremrangebyscore(self, key, lo, hi):
        d = self.z.get(key, {})
        for m in [m for m, s in d.items() if lo <= s <= hi]:
            del d[m]

    def zrangebyscore(self, key, lo, hi):
        d = self.z.get(key, {})
        return [m for m, s in sorted(d.items(), key=lambda kv: kv[1]) if lo <= s <= hi]


def test_record_and_read_roundtrip():
    r = FakeRedis()
    snaps = [("BTC_USDT", 1000, 100.0, 60000.0), ("BTC_USDT", 2000, 110.0, 60500.0)]
    n = record_oi_snapshots("redis://x", snaps, client=r)
    assert n == 2
    series = read_oi_series("redis://x", "BTC_USDT", 0, 9999, client=r)
    assert [d["oi"] for d in series] == [100.0, 110.0]
    assert series[1]["p"] == 60500.0


def test_old_snapshots_trimmed():
    r = FakeRedis()
    # newest=2_000_000ms, max_age=1s -> cutoff=1_999_000ms; the 1000ms entry is dropped
    record_oi_snapshots("redis://x", [("ETH_USDT", 1000, 1.0, 1.0)], client=r)
    record_oi_snapshots("redis://x", [("ETH_USDT", 2_000_000, 2.0, 2.0)], max_age_seconds=1, client=r)
    series = read_oi_series("redis://x", "ETH_USDT", 0, 10_000_000, client=r)
    assert [d["t"] for d in series] == [2_000_000]


def test_noop_without_client_or_snapshots():
    assert record_oi_snapshots("", [("BTC_USDT", 1, 1.0, 1.0)]) == 0
    assert record_oi_snapshots("redis://x", [], client=FakeRedis()) == 0
