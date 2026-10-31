import os
import sys
import unittest

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.services.room_manager import RoomManager, ConnectedPlayer


class TestRoomManager(unittest.TestCase):
    def setUp(self):
        self.manager = RoomManager()

    def test_create_and_get_room(self):
        room = self.manager.create_room(
            room_name="Apex Championship",
            track_id="silverstone",
            laps=7,
            weather="rain",
            collision="ghost",
            max_players=12,
            is_public=True,
        )
        self.assertIsNotNone(room.room_id)
        self.assertEqual(len(room.room_id), 6)
        self.assertEqual(room.name, "Apex Championship")

        retrieved = self.manager.get_room(room.room_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.room_id, room.room_id)

    def test_public_room_listing_and_filtering(self):
        r1 = self.manager.create_room(room_name="Public 1", is_public=True)
        r2 = self.manager.create_room(room_name="Private 1", is_public=False)

        public_summaries = self.manager.list_public_rooms()
        public_ids = [s.room_id for s in public_summaries]

        self.assertIn(r1.room_id, public_ids)
        self.assertNotIn(r2.room_id, public_ids)

    def test_player_and_slot_assignment(self):
        room = self.manager.create_room(room_name="Grand Prix", max_players=4)

        p1 = ConnectedPlayer(
            player_id="p_1",
            name="Max",
            team_id="redbull",
            car_model="f1_pro",
            car_color="#0000ff",
            driver_id="max_v",
        )
        p2 = ConnectedPlayer(
            player_id="p_2",
            name="Charles",
            team_id="scuderia",
            car_model="f1_pro",
            car_color="#ff0000",
            driver_id="charles_l",
        )
        p_spec = ConnectedPlayer(
            player_id="p_spec",
            name="Spectator 1",
            team_id="generic",
            car_model="f1_pro",
            car_color="#ffffff",
            driver_id="spec",
            is_spectator=True,
        )

        room.players[p1.player_id] = p1
        room.players[p2.player_id] = p2
        room.players[p_spec.player_id] = p_spec
        room.assign_slots()

        self.assertEqual(p1.slot, 0)
        self.assertEqual(p2.slot, 1)
        self.assertEqual(p_spec.slot, -1)  # Spectators don't take a racing slot

        summary = room.get_summary()
        self.assertEqual(summary.player_count, 2)
        self.assertEqual(summary.spectator_count, 1)

    def test_stale_room_cleanup(self):
        room = self.manager.create_room(room_name="Old Stale Room")
        # Artificially age the room by 4 hours (14,400s)
        room.created_at -= 15000
        self.manager.cleanup_stale_rooms()
        self.assertIsNone(self.manager.get_room(room.room_id))


if __name__ == "__main__":
    unittest.main()
