from math import floor, ceil
from typing import List

LEFT = "left"
RIGHT = "right"
CENTER = "center"


def rolling_average(
    data: List[float], window: int, alignment: str = CENTER
) -> List[float]:
    window_before = ceil(window / 2) - 1
    window_after = floor(window / 2)

    start = window_before
    end = len(data) - window_after - 1

    buf = data[:window]

    rolling_avg = []

    for i, d in enumerate(data):
        if start <= i <= end:
            if None in buf:
                rolling_avg.append(None)
            else:
                rolling_avg.append(sum(buf) / len(buf))

            buf.pop(0)
            if i + window_after + 1 < len(data):
                buf.append(data[i + window_after + 1])

        else:
            rolling_avg.append(None)

    match alignment:
        case "left":
            rolling_avg = rolling_avg[start:] + [None] * window_before
        case "right":
            rolling_avg = [None] * window_after + rolling_avg[: end + 1]
        case "center":
            pass
        case _:
            raise Exception(f"Unknown rolling average alignment: {alignment}")

    return rolling_avg
