from lighthouse.collectors.system import collect_system_snapshot

def test_collect_system_snapshot():
    snapshot = collect_system_snapshot()
    assert "cpu_percent" in snapshot
    assert "memory" in snapshot
    assert "disk" in snapshot
