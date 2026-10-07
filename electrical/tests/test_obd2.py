"""Decoder tests for the Orion OBD2 client.

The byte strings are replies captured from glorb's two Orion BMS 2 units on
2026-10-06 (master ECU 0x7E3, slave 0x7E4), so they pin down the real layout.
"""

import unittest

from glorbmon import obd2, slcan


class DtcDecoding(unittest.TestCase):
    def test_master_three_codes(self):
        self.assertEqual(obd2.decode_dtcs(bytes.fromhex("43030a800a040a0d")),
                         ["P0A80", "P0A04", "P0A0D"])

    def test_slave_one_code(self):
        self.assertEqual(obd2.decode_dtcs(bytes.fromhex("47010a04")), ["P0A04"])

    def test_no_codes(self):
        self.assertEqual(obd2.decode_dtcs(bytes.fromhex("4a00")), [])

    def test_letter_bits(self):
        self.assertEqual(obd2.decode_dtcs(bytes([0x43, 1, 0xC1, 0x00])), ["U0100"])

    def test_not_a_dtc_reply(self):
        self.assertIsNone(obd2.decode_dtcs(bytes.fromhex("62f00d0296")))
        self.assertIsNone(obd2.decode_dtcs(b""))

    def test_flag_words(self):
        self.assertEqual(obd2.decode_flags(0x0054, obd2.DTC_FLAGS_2), ["P0A80", "P0A04", "P0A0D"])
        self.assertEqual(obd2.decode_flags(0x0010, obd2.DTC_FLAGS_2), ["P0A04"])
        self.assertEqual(obd2.decode_flags(0, obd2.DTC_FLAGS_1), [])


class IsoTpReassembly(unittest.TestCase):
    def test_single_frame(self):
        asm = obd2.IsoTp()
        self.assertEqual(asm.feed(bytes.fromhex("0562f00d02960000")), bytes.fromhex("62f00d0296"))
        self.assertFalse(asm.need_flow_control)

    def test_multi_frame_needs_flow_control(self):
        asm = obd2.IsoTp()
        self.assertIsNone(asm.feed(bytes.fromhex("100843030a800a04")))
        self.assertTrue(asm.need_flow_control)
        self.assertEqual(asm.feed(bytes.fromhex("210a0d0000000000")), bytes.fromhex("43030a800a040a0d"))

    def test_consecutive_before_first_is_ignored(self):
        asm = obd2.IsoTp()
        self.assertIsNone(asm.feed(bytes.fromhex("210a0d0000000000")))


class ParameterDecoding(unittest.TestCase):
    def test_pack_voltage(self):
        self.assertEqual(obd2.decode_parameter(0x0D, bytes.fromhex("0296")), ("Pack Inst. Voltage (V)", 66.2))

    def test_cell_voltage_scale(self):
        self.assertEqual(obd2.decode_parameter(0x33, bytes.fromhex("c92a")), ("High Cell Voltage (V)", 5.1498))

    def test_signed_current(self):
        self.assertEqual(obd2.decode_parameter(0x0C, bytes.fromhex("fff6"))[1], -1.0)

    def test_half_percent_soc(self):
        self.assertEqual(obd2.decode_parameter(0x0F, bytes.fromhex("63"))[1], 49.5)

    def test_unknown_parameter_is_hex(self):
        self.assertEqual(obd2.decode_parameter(0xFD, bytes.fromhex("0b200a23"))[1], "0b200a23")

    def test_cell_block(self):
        block = bytes.fromhex("90a7" "9090" "7f9d" "9d6f" "6033" "bf52")
        values = obd2.decode_cell_block(block)
        self.assertEqual(values[:2], [0x90A7, 0x9090])
        self.assertEqual(len(values), 6)


class FakeSerial:
    def __init__(self):
        self.written = []

    def write(self, data):
        self.written.append(data)

    def flush(self):
        pass


class SlcanSend(unittest.TestCase):
    def test_request_frame_layout(self):
        port = slcan.SlcanPort(lambda **kw: FakeSerial())
        port.ser = FakeSerial()
        port.send(0x7E3, bytes([0x03, 0x22, 0xF0, 0x0D, 0, 0, 0, 0]))
        self.assertEqual(port.ser.written, [b"t7E380322F00D00000000\r"])

    def test_extended_frame_layout(self):
        port = slcan.SlcanPort(lambda **kw: FakeSerial())
        port.ser = FakeSerial()
        port.send(0x1806E5F4, bytes([1, 2]), extended=True)
        self.assertEqual(port.ser.written, [b"T1806E5F420102\r"])

    def test_refuses_when_closed(self):
        port = slcan.SlcanPort(lambda **kw: FakeSerial())
        with self.assertRaises(slcan.SlcanError):
            port.send(0x7E3, b"\x01\x03")


if __name__ == "__main__":
    unittest.main()
