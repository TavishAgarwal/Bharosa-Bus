import importlib
import pytest

STAGES = ["gps_check"]


@pytest.mark.parametrize("name", STAGES)
def test_stage_is_stub(name):
    mod = importlib.import_module(f"bharosa.{name}")
    with pytest.raises(NotImplementedError):
        mod.run()
