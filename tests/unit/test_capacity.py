import pytest

from people_counter.domain.model import CapacityMonitor, CapacityStatus, OccupancyCounter, capacity_status


def test_room_status_depends_on_how_full_it_is():
    assert capacity_status(10, capacity=40) == CapacityStatus.OK
    assert capacity_status(32, capacity=40) == CapacityStatus.NEAR
    assert capacity_status(40, capacity=40) == CapacityStatus.FULL
    assert capacity_status(41, capacity=40) == CapacityStatus.OVER


def test_one_person_in_a_room_for_one_is_full_not_almost_full():
    assert capacity_status(1, capacity=1) == CapacityStatus.FULL
    assert capacity_status(0, capacity=1) == CapacityStatus.OK


def test_reports_when_the_room_goes_over_capacity():
    monitor = CapacityMonitor(capacity=40)

    event = monitor.check(41)

    assert event is not None
    assert (event.exceeded, event.count, event.capacity) == (True, 41, 40)


def test_reports_each_crossing_only_once():
    monitor = CapacityMonitor(capacity=40)

    events = [monitor.check(count) for count in (30, 41, 42, 43, 38, 37)]

    assert [(e.exceeded, e.count) for e in events if e] == [(True, 41), (False, 38)]


def test_lowering_the_capacity_can_put_the_room_over_it():
    monitor = CapacityMonitor(capacity=40)
    assert monitor.check(20) is None

    monitor.capacity = 15

    event = monitor.check(20)
    assert event is not None and event.exceeded


def test_smoothing_window_needs_at_least_one_frame():
    with pytest.raises(ValueError):
        OccupancyCounter(window=0)
