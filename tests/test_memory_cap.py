# SPDX-FileCopyrightText: 2026 Plasma Theme Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The test run itself is capped (tests/conftest.py), so that code which believes a
hostile file fails here instead of filling the machine's memory."""

from pathlib import Path

import pytest

resource = pytest.importorskip("resource")


def test_a_runaway_allocation_fails_inside_the_test_run():
    soft, _hard = resource.getrlimit(resource.RLIMIT_AS)
    if soft == resource.RLIM_INFINITY or soft > 16 * 1024**3:
        pytest.skip("the memory cap is off (PTS_TEST_MEMORY_CAP)")
    with pytest.raises(MemoryError):
        bytearray(40 * 1024**3)


def test_the_test_run_is_the_first_to_go_when_memory_runs_out():
    score = Path("/proc/self/oom_score_adj")
    if not score.exists():
        pytest.skip("no /proc")
    assert score.read_text().strip() == "1000"
