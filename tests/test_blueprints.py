from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from jinja2 import Environment
import yaml

BLUEPRINT_DIR = (
    Path(__file__).parents[1] / "blueprints" / "automation" / "sec_smart"
)
ADAPTIVE_BLUEPRINTS = (
    BLUEPRINT_DIR / "free_cooling_overlay.yaml",
    BLUEPRINT_DIR / "absolute_humidity_overlay.yaml",
)


class BlueprintLoader(yaml.SafeLoader):
    pass


BlueprintLoader.add_constructor(
    "!input", lambda loader, node: loader.construct_scalar(node)
)


def load_blueprint(path: Path) -> dict[str, object]:
    result = yaml.load(path.read_text(encoding="utf-8"), Loader=BlueprintLoader)
    assert isinstance(result, dict)
    return result


def template_strings(value: object) -> Iterator[str]:
    if isinstance(value, str) and ("{{" in value or "{%" in value):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from template_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from template_strings(nested)


def test_all_blueprints_parse_and_declare_automation_domain() -> None:
    for path in BLUEPRINT_DIR.glob("*.yaml"):
        data = load_blueprint(path)
        assert data["blueprint"]["domain"] == "automation"
        assert data["blueprint"]["source_url"].endswith(path.name)


def test_all_blueprint_templates_parse_as_jinja() -> None:
    environment = Environment()
    for path in BLUEPRINT_DIR.glob("*.yaml"):
        for template in template_strings(load_blueprint(path)):
            environment.parse(template)


def test_adaptive_blueprints_include_control_safety_guards() -> None:
    for path in ADAPTIVE_BLUEPRINTS:
        text = path.read_text(encoding="utf-8")
        data = load_blueprint(path)
        inputs = data["blueprint"]["input"]

        assert "is_number(states(" in text
        assert "| float(0)" not in text
        assert "thresholds_valid" in text
        assert "minimum_dwell_minutes" in inputs
        assert "adaptive_state" in inputs
        assert "override_entity" in inputs
        assert "connection_sensor" in inputs
        assert "schedule_entity" in inputs
        assert "wait_template" in text
        assert "schedule.block_started" in text
        assert data["mode"] == "queued"


def test_absolute_humidity_blueprint_uses_all_four_environment_sensors() -> None:
    text = ADAPTIVE_BLUEPRINTS[1].read_text(encoding="utf-8")
    for sensor in (
        "indoor_temperature_sensor",
        "indoor_humidity_sensor",
        "outdoor_temperature_sensor",
        "outdoor_humidity_sensor",
    ):
        assert sensor in text

    assert "216.7" in text
    assert "273.15" in text
    assert "start_absolute_humidity_difference" in text
    assert "stop_absolute_humidity_difference" in text
