from swash.util import decimal, blank
from rdflib.namespace import TIME


def make_duration(seconds: float):
    return blank(
        TIME.Duration,
        {
            TIME.numericDuration: decimal(seconds),
            TIME.unitType: TIME.unitSecond,
        },
    )


def make_instant(timeline, seconds: float):
    return blank(
        TIME.Instant,
        {
            TIME.inTimePosition: blank(
                TIME.TimePosition,
                {
                    TIME.numericPosition: decimal(seconds),
                    TIME.unitType: TIME.unitSecond,
                    TIME.hasTRS: timeline,
                },
            )
        },
    )


def make_interval(timeline, start, duration):
    return blank(
        TIME.Interval,
        {
            TIME.hasTRS: timeline,
            TIME.hasBeginning: make_instant(timeline, start),
            TIME.hasDuration: make_duration(duration),
        },
    )
