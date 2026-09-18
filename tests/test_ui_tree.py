from pathlib import Path

from android.observation import ObservationBuilder
from android.ui_tree import parse_bounds, parse_ui_hierarchy


FIXTURE = Path("tests/fixtures/sample_ui.xml")


def test_parse_sample_ui() -> None:
    elements = parse_ui_hierarchy(FIXTURE)
    assert elements
    login = next(el for el in elements if el.text == "Login")
    assert login.type == "android.widget.Button"
    assert login.content_description == "Login"
    assert login.clickable is True
    assert login.enabled is True
    assert login.scrollable is False
    assert login.bounds is not None
    assert login.bounds.to_dict() == {"left": 100, "top": 400, "right": 500, "bottom": 480}
    assert login.element_id == "element_000004"
    assert all(el.element_id.startswith("element_") for el in elements)


def test_parse_bounds() -> None:
    bounds = parse_bounds("[-1,2][3,4]")
    assert bounds is not None
    assert bounds.left == -1
    assert bounds.bottom == 4


def test_missing_properties_use_defaults() -> None:
    xml = """
    <hierarchy>
      <node class="android.view.View" bounds="[0,0][10,10]"/>
    </hierarchy>
    """
    elements = parse_ui_hierarchy(xml)
    assert len(elements) == 1
    el = elements[0]
    assert el.text is None
    assert el.clickable is False
    assert el.enabled is True
    assert el.element_id == "element_000001"
