from people_counter.domain.model import BoundingBox, Detection, OccupancyCounter


def person(confidence: float = 0.9) -> Detection:
    return Detection(BoundingBox(0, 0, 10, 20), confidence)


def test_empty_room_has_zero_people():
    counter = OccupancyCounter(window=1)

    occupancy = counter.update([])

    assert occupancy.count == 0
    assert occupancy.people == ()


def test_counts_people_detected_in_a_frame():
    counter = OccupancyCounter(window=1)

    occupancy = counter.update([person(), person(), person()])

    assert occupancy.count == 3


def test_ignores_low_confidence_detections():
    counter = OccupancyCounter(min_confidence=0.5, window=1)

    occupancy = counter.update([person(0.9), person(0.3)])

    assert occupancy.count == 1
    assert occupancy.people == (person(0.9),)


def test_a_person_missed_for_one_frame_does_not_change_the_count():
    counter = OccupancyCounter(window=5)
    for _ in range(4):
        counter.update([person(), person()])

    occupancy = counter.update([person()])

    assert occupancy.count == 2


def test_count_changes_when_someone_really_leaves():
    counter = OccupancyCounter(window=5)
    for _ in range(5):
        counter.update([person(), person()])

    for _ in range(3):
        occupancy = counter.update([person()])

    assert occupancy.count == 1


def test_remembers_the_peak_occupancy():
    counter = OccupancyCounter(window=1)
    counter.update([person()] * 4)

    occupancy = counter.update([person()])

    assert occupancy.count == 1
    assert occupancy.peak == 4
