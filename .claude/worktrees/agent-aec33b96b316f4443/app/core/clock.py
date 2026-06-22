from datetime import datetime, timezone


class Clock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


clock = Clock()


def get_clock() -> Clock:
    return clock
