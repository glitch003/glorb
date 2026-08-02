import struct
import unittest
from unittest.mock import MagicMock, patch

from glorbleds.e131 import Sender, build_packet, iface_for, send_span


CID = bytes(range(16))


class InterfaceDetectionTests(unittest.TestCase):
    def test_socket_creation_failure_returns_no_interface(self):
        with patch("glorbleds.e131.socket.socket", side_effect=OSError("denied")):
            self.assertIsNone(iface_for("192.0.2.1"))


class PacketFormatTests(unittest.TestCase):
    def test_full_universe_packet_has_standard_length_and_fields(self):
        dmx = bytes(i % 256 for i in range(510))
        packet = build_packet(321, dmx, 17, CID, "glorb-test")

        self.assertEqual(len(packet), 638)
        self.assertEqual(struct.unpack("!H", packet[0:2])[0], 0x0010)
        self.assertEqual(struct.unpack("!H", packet[2:4])[0], 0)
        self.assertEqual(packet[4:16], b"ASC-E1.17\0\0\0")
        self.assertEqual(struct.unpack("!H", packet[16:18])[0], 0x7000 | 622)
        self.assertEqual(struct.unpack("!I", packet[18:22])[0], 0x00000004)
        self.assertEqual(packet[22:38], CID)
        self.assertEqual(struct.unpack("!H", packet[38:40])[0], 0x7000 | 600)
        self.assertEqual(struct.unpack("!I", packet[40:44])[0], 0x00000002)
        self.assertEqual(packet[44:108], b"glorb-test" + bytes(54))
        self.assertEqual(packet[108], 100)
        self.assertEqual(struct.unpack("!H", packet[109:111])[0], 0)
        self.assertEqual(packet[111], 17)
        self.assertEqual(packet[112], 0)
        self.assertEqual(struct.unpack("!H", packet[113:115])[0], 321)
        self.assertEqual(struct.unpack("!H", packet[115:117])[0], 0x7000 | 523)
        self.assertEqual(packet[117], 0x02)
        self.assertEqual(packet[118], 0xA1)
        self.assertEqual(struct.unpack("!H", packet[119:121])[0], 0)
        self.assertEqual(struct.unpack("!H", packet[121:123])[0], 1)
        self.assertEqual(struct.unpack("!H", packet[123:125])[0], 513)
        self.assertEqual(packet[125], 0)
        self.assertEqual(packet[126:636], dmx)
        self.assertEqual(packet[636:], b"\0\0")

    def test_invalid_universe_is_rejected(self):
        for universe in (0, 64000):
            with self.subTest(universe=universe):
                with self.assertRaises(ValueError):
                    build_packet(universe, b"", 0, CID)

    def test_cid_must_be_exactly_sixteen_bytes(self):
        for cid in (b"short", bytes(17)):
            with self.subTest(length=len(cid)):
                with self.assertRaises(ValueError):
                    build_packet(1, b"", 0, cid)


class SpanTests(unittest.TestCase):
    class RecordingSender:
        def __init__(self):
            self.calls = []

        def send(self, universe, dmx):
            self.calls.append((universe, dmx))

    def test_span_splits_at_170_rgb_pixels(self):
        sender = self.RecordingSender()
        data = bytes(i % 256 for i in range(1120 * 3))

        send_span(sender, 8, data)

        self.assertEqual([u for u, _ in sender.calls], list(range(8, 15)))
        self.assertEqual([len(d) for _, d in sender.calls], [510] * 6 + [300])
        self.assertEqual(b"".join(d for _, d in sender.calls), data)


class SenderSequenceTests(unittest.TestCase):
    class RecordingSocket:
        def __init__(self):
            self.packets = []

        def setsockopt(self, *args):
            pass

        def sendto(self, packet, dest):
            self.packets.append((packet, dest))

        def close(self):
            pass

    def test_sequences_advance_independently_per_universe(self):
        sender = Sender.__new__(Sender)
        sender.host = "127.0.0.1"
        sender.source_name = "test"
        sender.cid = CID
        sender._seq = {}
        sender.sock = self.RecordingSocket()

        sender.send(1, b"a")
        sender.send(2, b"b")
        sender.send(1, b"c")

        self.assertEqual([p[111] for p, _ in sender.sock.packets], [1, 1, 2])

    def test_sender_uses_nonblocking_udp_for_latency_first_output(self):
        sock = MagicMock()
        with patch("glorbleds.e131.socket.socket", return_value=sock):
            sender = Sender(host="127.0.0.1")

        sock.setblocking.assert_called_once_with(False)
        sender.close()


if __name__ == "__main__":
    unittest.main()
