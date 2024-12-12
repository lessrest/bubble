from swash.util import decimal


from rdflib.namespace import TIME
from swash.util import new


def make_duration(seconds: float):
    return new(
        TIME.Duration,
        {
            TIME.numericDuration: decimal(seconds),
            TIME.unitType: TIME.unitSecond,
        },
    )


def make_instant(timeline, seconds: float):
    return new(
        TIME.Instant,
        {
            TIME.inTimePosition: new(
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
    return new(
        TIME.Interval,
        {
            TIME.hasTRS: timeline,
            TIME.hasBeginning: make_instant(timeline, start),
            TIME.hasDuration: make_duration(duration),
        },
    )
