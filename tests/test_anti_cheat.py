import unittest
from app.services.anti_cheat import validate_lap_time, validate_ghost_telemetry


class TestAntiCheat(unittest.TestCase):
    def test_minimum_physics_threshold(self):
        # Under 3.0 seconds (180 ticks) is impossible on any track
        self.assertFalse(validate_lap_time("Default", 100))
        self.assertFalse(validate_lap_time("Monaco", 150))

    def test_circuit_specific_thresholds(self):
        # Monaco record threshold is 1400 ticks
        self.assertFalse(validate_lap_time("Monaco", 1200))
        self.assertTrue(validate_lap_time("Monaco", 1550))

        # Silverstone record threshold is 1600 ticks
        self.assertFalse(validate_lap_time("Silverstone", 1500))
        self.assertTrue(validate_lap_time("Silverstone", 1750))

    def test_sector_sum_drift(self):
        # 3000 ticks = 50.0 seconds
        valid_sectors = [15.0, 18.0, 17.0]  # Sum = 50.0
        self.assertTrue(validate_lap_time("Silverstone", 3000, valid_sectors))

        # Cheated sectors sum = 40.0s vs 50.0s lap
        tampered_sectors = [10.0, 15.0, 15.0]
        self.assertFalse(validate_lap_time("Silverstone", 3000, tampered_sectors))

    def test_ghost_telemetry_density(self):
        # 60s lap (3600 ticks) with only 3 frames -> rejected
        sparse_ghost = [{"x": 0, "y": 0, "speed": 100}, {"x": 10, "y": 10, "speed": 100}, {"x": 20, "y": 20, "speed": 100}]
        self.assertFalse(validate_ghost_telemetry(sparse_ghost, 3600))

    def test_ghost_telemetry_speed_cap(self):
        # 10s lap (600 ticks) -> expected min frames ~30
        excessive_speed_ghost = [
            {"x": float(i * 5), "y": float(i * 5), "speed": 550.0}  # 550 km/h > 430 km/h
            for i in range(40)
        ]
        self.assertFalse(validate_ghost_telemetry(excessive_speed_ghost, 600))

    def test_ghost_telemetry_teleportation(self):
        frames = [{"x": float(i * 2), "y": 0.0, "speed": 200.0} for i in range(25)]
        # Warp jump of 600 meters in a single tick
        frames.append({"x": 800.0, "y": 0.0, "speed": 200.0})
        frames.extend([{"x": 800.0 + float(i * 2), "y": 0.0, "speed": 200.0} for i in range(15)])
        self.assertFalse(validate_ghost_telemetry(frames, 600))

    def test_ghost_telemetry_valid(self):
        valid_frames = [
            {"x": float(i * 2), "y": float(i), "speed": 220.0}
            for i in range(50)
        ]
        self.assertTrue(validate_ghost_telemetry(valid_frames, 600))


if __name__ == "__main__":
    unittest.main()

