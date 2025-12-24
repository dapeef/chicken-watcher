from hardware_agent import add, sub


def test_string():
    assert "py" in "pytest"


def test_add():
    assert add(1, 2) == 3


def test_sub():
    assert sub(1, 2) == -1
