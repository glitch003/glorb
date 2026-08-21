import unittest
from unittest.mock import patch

from glorbleds.ddp import MAX_DATA, DDPSender, build_packet


class PacketFormatTests(unittest.TestCase):
    def test_header_fields_and_push_flag(self):
        data = bytes(range(3)) * 10
        pkt = build_packet(5040, data, 7, push=True)

        self.assertEqual(pkt[0], 0x41)              # ver1 | push
        self.assertEqual(pkt[1], 7)                 # sequence
        self.assertEqual(pkt[3], 0x01)              # default output device
        self.assertEqual(int.from_bytes(pkt[4:8], "big"), 5040)
        self.assertEqual(int.from_bytes(pkt[8:10], "big"), len(data))
        self.assertEqual(pkt[10:], data)

    def test_no_push_flag_on_intermediate_packets(self):
        pkt = build_packet(0, b"\x01\x02\x03", 1, push=False)
        self.assertEqual(pkt[0], 0x40)

    def test_oversized_data_is_rejected(self):
        with self.assertRaises(ValueError):
            build_packet(0, bytes(MAX_DATA + 1), 1, push=True)

    def test_empty_data_is_rejected(self):
        with self.assertRaises(ValueError):
            build_packet(0, b"", 1, push=True)


class SenderTests(unittest.TestCase):
    """fppd latches its outputs when (and only when) a PUSH packet arrives,
    so exactly the final packet of every frame must carry the flag, and
    sequence numbers must cycle 1..15 or fppd counts them as loss."""

    def make_sender(self):
        with patch("glorbleds.ddp.socket.socket"):
            sender = DDPSender("192.0.2.1")
        self.sent = []
        sender.sock.sendto = lambda pkt, dest: self.sent.append((pkt, dest))
        return sender

    def test_frame_splits_on_whole_pixels_with_push_on_last(self):
        sender = self.make_sender()
        nbytes = MAX_DATA * 2 + 300
        sender.send_pixels(1, bytes(nbytes))

        self.assertEqual(len(self.sent), 3)
        self.assertEqual([p[0] & 0x01 for p, _ in self.sent], [0, 0, 1])
        self.assertEqual([int.from_bytes(p[4:8], "big") for p, _ in self.sent],
                         [0, MAX_DATA, MAX_DATA * 2])
        self.assertEqual(sum(int.from_bytes(p[8:10], "big")
                             for p, _ in self.sent), nbytes)
        self.assertEqual(MAX_DATA % 3, 0)

    def test_start_universe_maps_to_510_channel_offset(self):
        sender = self.make_sender()
        sender.send_pixels(3, bytes(30))
        self.assertEqual(int.from_bytes(self.sent[0][0][4:8], "big"), 2 * 510)

    def test_sequence_cycles_one_to_fifteen(self):
        sender = self.make_sender()
        for _ in range(20):
            sender.send_pixels(1, bytes(3))
        seqs = [p[1] for p, _ in self.sent]
        self.assertEqual(seqs[:16], list(range(1, 16)) + [1])
        self.assertNotIn(0, seqs)

    def test_single_packet_frame_is_pushed(self):
        sender = self.make_sender()
        sender.send_pixels(1, bytes(MAX_DATA))
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][0][0] & 0x01, 1)

    def test_requires_a_host(self):
        with self.assertRaises(ValueError):
            DDPSender("")

    def test_host_down_is_counted_not_raised(self):
        """The controller shares a power strip with the tubes and gets
        power-cycled on the bench; a dead host must not kill the send loop."""
        sender = self.make_sender()
        def boom(pkt, dest):
            raise OSError(64, "Host is down")
        sender.sock.sendto = boom
        sender.send_pixels(1, bytes(MAX_DATA + 30))   # 2 packets
        self.assertEqual(sender.dropped_packets, 2)


if __name__ == "__main__":
    unittest.main()
