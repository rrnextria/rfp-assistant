"""Smoke tests for plan test fixtures."""
from pathlib import Path


def test_complex_plan_fixture_is_directory(complex_plan_fixture):
    assert isinstance(complex_plan_fixture, Path)
    assert complex_plan_fixture.is_dir()


def test_simple_plan_fixture_is_file(simple_plan_fixture):
    assert isinstance(simple_plan_fixture, Path)
    assert simple_plan_fixture.is_file()


def test_malformed_plan_is_dict_of_paths(malformed_plan):
    assert isinstance(malformed_plan, dict)
    for name, path in malformed_plan.items():
        assert isinstance(name, str)
        assert isinstance(path, Path)
        assert path.exists(), f"Malformed plan '{name}' does not exist at {path}"


def test_parsed_plan_is_nonempty_string(parsed_plan):
    assert isinstance(parsed_plan, str)
    assert len(parsed_plan) > 0


def test_fixtures_dir_is_directory(fixtures_dir):
    assert isinstance(fixtures_dir, Path)
    assert fixtures_dir.is_dir()


def test_count_tasks_per_phase_all_markers(tmp_path):
    """Verify _count_tasks_per_phase handles [ ], [x], and [✅] markers."""
    # Create a fake phase file with all 3 marker types
    phase_dir = tmp_path / "phases"
    phase_dir.mkdir(parents=True)
    phase_file = phase_dir / "phase_0_test.md"
    phase_file.write_text(
        "# Phase 0: Test\n\n"
        "## Tasks\n\n"
        "### [ ] 1 Pending Task\n\n"
        "### [x] 2 Done Task\n\n"
        "### [\u2705] 3 Emoji Done Task\n"
    )

    import re
    task_re = re.compile(r"^### \[[ x\u2705]\] (\d+)")
    task_numbers = set()
    for line in phase_file.read_text().splitlines():
        m = task_re.match(line)
        if m:
            task_numbers.add(int(m.group(1)))
    assert len(task_numbers) == 3
    assert task_numbers == {1, 2, 3}
