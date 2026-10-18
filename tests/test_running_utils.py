import unittest

from bot.utils.running import (
    calculate_pace,
    format_distance,
    format_duration,
    to_meters,
    to_seconds,
    validate_run,
)


class RunningUtilsTests(unittest.TestCase):
    def test_distance(self):
        self.assertEqual(to_meters("5km"), 5000)
        self.assertEqual(to_meters("1.5 k"), 1500)
        self.assertEqual(to_meters("1500m"), 1500)
        self.assertEqual(to_meters("0.1km"), 100)

    def test_bad_distance(self):
        for value in ["1.001m", "-2km", "0km", "3mi", "abc"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                to_meters(value)

    def test_duration(self):
        self.assertEqual(to_seconds("25:30"), 1530)
        self.assertEqual(to_seconds("1:05:30"), 3930)
        self.assertEqual(to_seconds("75:00"), 4500)
        self.assertEqual(format_duration(3930), "1:05:30")
        self.assertEqual(format_duration(1530), "25:30")

    def test_bad_duration(self):
        for value in ["00:00", "10:60", "1:60:00", "1:2:3:4", "-1:00"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                to_seconds(value)

    def test_validation(self):
        self.assertEqual(validate_run(" Morning ", "5km", "25:00"), ("Morning", 5000, 1500))
        self.assertEqual(format_distance(12500), "12.5 km")
        self.assertEqual(calculate_pace(5000, 1500), 300)
        for name, distance, duration in [
            ("", "5km", "25:00"),
            ("A" * 21, "5km", "25:00"),
            ("Easy", "500m", "3:00"),
            ("Easy", "5km", "1:00"),
            ("Easy", "5km", "2:00:00"),
        ]:
            with self.subTest(name=name, distance=distance, duration=duration), self.assertRaises(ValueError):
                validate_run(name, distance, duration)


if __name__ == "__main__":
    unittest.main()
