import pandas as pd

from apex.core.schemas import OPENF1_CAR_DATA


def _car_frame(gears: list[int]) -> pd.DataFrame:
    n = len(gears)
    return pd.DataFrame(
        {
            "date": ["2025-03-16T05:00:00.000000+00:00"] * n,
            "session_key": [9689] * n,
            "meeting_key": [1229] * n,
            "driver_number": [4] * n,
            "speed": [150] * n,
            "rpm": [10000] * n,
            "n_gear": gears,
            "throttle": [50] * n,
            "brake": [0] * n,
            "drs": [0] * n,
        }
    )


def test_out_of_range_gear_is_not_fatal_to_schema() -> None:
    # 2025 Melbourne reported gears up to 49 on some samples (sensor glitch)
    OPENF1_CAR_DATA.validate(_car_frame([3, 4, 49, 5]))
