"""Parser tests for the three battery protocols.

Where a test uses a byte string captured from the real hardware on the playa
(2026-09-02) it says so, because those cases are the ones that pin the field
layouts down -- everything else is a synthesised edge case.
"""

import unittest

from glorbmon import eg4, hub, orion, ports, slcan, soc, teslabms


# Replies captured from glorb's three 12 V packs on 2026-09-02.
EG4_PACK1 = bytes.fromhex(
    "01034e054203fb0d260d290d2a0d2100000000000000000000000000000000000000"
    "0000000000001800150015005800640064001600010000000000000000000155d4a8"
    "00151500000000000403e800006694")
EG4_PACK2 = bytes.fromhex(
    "02034e05420b050d250d270d280d2300000000000000000000000000000000000000"
    "0000000000001800150015010800640064004200010000000000000000000355d4a8"
    "00151500000000000403e80000a345")
EG4_PACK3 = bytes.fromhex(
    "03034e054106fb0d230d240d240d2100000000000000000000000000000000000000"
    "000000000000170015001500a800640064002a00010000000000000000000455d4a8"
    "00151500000000000403e8000017af")


def eg4_with(frame, **fields):
    """Rebuild a captured reply with some 16-bit fields replaced."""
    body = bytearray(frame[:-2])
    for name, value in fields.items():
        at = getattr(eg4, name)
        body[at:at + 2] = int(value).to_bytes(2, "big", signed=value < 0)
    return bytes(body) + eg4.crc16(bytes(body)).to_bytes(2, "little")


class TestEG4Request(unittest.TestCase):
    def test_request_is_a_modbus_read_of_39_registers(self):
        body = bytes.fromhex("010300000027")
        self.assertEqual(eg4.build_request(1),
                         body + eg4.crc16(body).to_bytes(2, "little"))

    def test_every_address_gets_a_valid_crc(self):
        for addr in (1, 2, 3, 16, 247):
            self.assertTrue(eg4.check_crc(eg4.build_request(addr)))
            self.assertEqual(eg4.build_request(addr)[0], addr)

    def test_address_must_be_a_valid_modbus_id(self):
        for bad in (0, 248, -1):
            with self.assertRaises(ValueError):
                eg4.build_request(bad)


class TestEG4Parse(unittest.TestCase):
    def test_captured_replies_pass_their_own_crc(self):
        for frame in (EG4_PACK1, EG4_PACK2, EG4_PACK3):
            self.assertTrue(eg4.check_crc(frame))

    def test_decodes_a_captured_reply(self):
        reading = eg4.parse_status(EG4_PACK1)
        self.assertEqual(reading["addr"], 1)
        self.assertTrue(reading["online"])
        self.assertEqual(reading["voltage"], 13.46)
        self.assertEqual(reading["cells"], [3.366, 3.369, 3.370, 3.361])
        self.assertEqual(reading["soc"], 22.0)
        self.assertEqual(reading["soh"], 100.0)
        self.assertEqual(reading["capacity_ah"], 88.0)
        self.assertEqual(reading["capacity_full_ah"], 400.0)
        self.assertEqual(reading["cycles"], 1)
        self.assertEqual(reading["temps"], [21, 21])
        self.assertEqual(reading["alarms"], [])

    def test_cells_sum_to_the_reported_pack_voltage(self):
        # One of the two cross-checks that pin the register offsets down.
        for frame in (EG4_PACK1, EG4_PACK2, EG4_PACK3):
            reading = eg4.parse_status(frame)
            self.assertAlmostEqual(sum(reading["cells"]), reading["voltage"],
                                   delta=0.02)

    def test_remaining_over_full_reproduces_the_reported_soc(self):
        # The other one: 88/400 = 22%, 264/400 = 66%, 168/400 = 42%.
        for frame in (EG4_PACK1, EG4_PACK2, EG4_PACK3):
            reading = eg4.parse_status(frame)
            ratio = reading["capacity_ah"] / reading["capacity_full_ah"] * 100
            self.assertAlmostEqual(ratio, reading["soc"], delta=0.5)

    def test_current_is_signed_and_positive_means_charging(self):
        self.assertAlmostEqual(eg4.parse_status(EG4_PACK1)["current"],
                               10.19, places=2)
        discharging = eg4_with(EG4_PACK1, O_CURRENT=-1019)
        self.assertAlmostEqual(eg4.parse_status(discharging)["current"],
                               -10.19, places=2)

    def test_cell_spread(self):
        reading = eg4.parse_status(EG4_PACK1)
        self.assertEqual(reading["cell_min"], 3.361)
        self.assertEqual(reading["cell_max"], 3.370)
        self.assertAlmostEqual(reading["cell_delta_mv"], 9.0, places=6)

    def test_set_protection_and_error_words_raise_alarms(self):
        reading = eg4.parse_status(eg4_with(EG4_PACK1, O_PROTECTION=0x0040))
        self.assertEqual(reading["alarms"], ["protection word 0x0040"])
        reading = eg4.parse_status(eg4_with(EG4_PACK1, O_ERROR=0x0002))
        self.assertEqual(reading["alarms"], ["error word 0x0002"])

    def test_cell_count_drives_how_many_cells_are_read(self):
        # A 4-cell pack must not report the twelve zero words that follow.
        self.assertEqual(len(eg4.parse_status(EG4_PACK1)["cells"]), 4)

    def test_rejects_a_corrupted_reply(self):
        bad = bytearray(EG4_PACK1)
        bad[10] ^= 0xFF
        with self.assertRaises(ValueError):
            eg4.parse_status(bytes(bad))

    def test_rejects_short_and_malformed_replies(self):
        for bad in (b"", b"\x01\x03", bytes(83)):
            with self.assertRaises(ValueError):
                eg4.parse_status(bad)

    def test_reports_a_modbus_exception_rather_than_decoding_it(self):
        body = b"\x01\x83\x02"
        frame = body + eg4.crc16(body).to_bytes(2, "little")
        with self.assertRaises(ValueError) as ctx:
            eg4.parse_status(frame)
        self.assertIn("exception", str(ctx.exception))


class FakeSerial:
    """Just enough pyserial surface for the framing tests."""

    def __init__(self, data=b""):
        self.buffer = bytearray(data)
        self.written = bytearray()
        self.resets = 0

    def read(self, n):
        chunk = bytes(self.buffer[:n])
        del self.buffer[:n]
        return chunk

    def write(self, data):
        self.written += data
        return len(data)

    def flush(self):
        pass

    def reset_input_buffer(self):
        self.resets += 1
        self.buffer.clear()

    @property
    def in_waiting(self):
        return len(self.buffer)

    def close(self):
        pass


class TestEG4Framing(unittest.TestCase):
    def test_byte_count_bounds_the_read(self):
        # A second reply queued behind the first must not be swallowed.
        ser = FakeSerial(EG4_PACK1 + EG4_PACK2)
        self.assertEqual(eg4.read_frame(ser), EG4_PACK1)
        self.assertEqual(eg4.read_frame(ser), EG4_PACK2)

    def test_truncated_reply_raises_and_resyncs(self):
        ser = FakeSerial(EG4_PACK1[:40])
        with self.assertRaises(ValueError):
            eg4.read_frame(ser)
        self.assertEqual(ser.resets, 1)

    def test_exception_reply_is_read_whole(self):
        body = b"\x01\x83\x02"
        frame = body + eg4.crc16(body).to_bytes(2, "little")
        self.assertEqual(eg4.read_frame(FakeSerial(frame)), frame)

    def test_silence_reads_as_no_frame(self):
        self.assertIsNone(eg4.read_frame(FakeSerial(b"")))


class TestEG4Bus(unittest.TestCase):
    def test_a_silent_pack_does_not_hide_the_others(self):
        # Pack 2 never answers; 1 and 3 must still be reported.
        ser = FakeSerial()
        replies = {1: EG4_PACK1, 2: b"", 3: EG4_PACK3}

        def write(data):
            ser.buffer += replies.get(data[0], b"")
            return len(data)

        ser.write = write
        bus = eg4.EG4Bus(lambda **kw: ser, gap_s=0)
        payload, raw = bus.poll()
        self.assertEqual(payload["state"], "warn")
        self.assertIn("silent: 2", payload["status_text"])
        online = [p["addr"] for p in payload["packs"] if p.get("online")]
        self.assertEqual(online, [1, 3])

    def test_bank_soc_comes_from_summed_amp_hours(self):
        ser = FakeSerial()
        replies = {1: EG4_PACK1, 2: EG4_PACK2, 3: EG4_PACK3}

        def write(data):
            ser.buffer += replies.get(data[0], b"")
            return len(data)

        ser.write = write
        payload, _ = eg4.EG4Bus(lambda **kw: ser, gap_s=0).poll()
        self.assertEqual(payload["state"], "ok")
        values = {s["label"]: s["value"] for s in payload["summary"]}
        # 88 + 264 + 168 = 520 Ah of 1200 Ah
        self.assertEqual(values["Remaining"], "520")
        self.assertEqual(values["SOC"], "43")
        # 10.19 + 28.21 + 17.87 A, all three charging
        self.assertEqual(values["Current"], "+56.3")
        self.assertEqual(values["Bus"], "13.46")


TESLA_LINE = ("INV,1,24.4418,4.0896,4.0930,4.0930,4.0934,4.0930,4.0923,"
              "18.39,17.74,0,0,0,0")


class TestTeslaBMS(unittest.TestCase):
    def test_parses_a_line_captured_from_the_due(self):
        module = teslabms.parse_inventory_line(TESLA_LINE)
        self.assertEqual(module["addr"], 1)
        self.assertEqual(module["voltage"], 24.4418)
        self.assertEqual(len(module["cells"]), 6)
        self.assertEqual(module["cells"][0], 4.0896)
        self.assertEqual(module["temps"], [18.39, 17.74])
        self.assertEqual(module["flags"], [])
        self.assertAlmostEqual(module["cell_delta_mv"], 3.8, places=3)

    def test_status_words_are_hex(self):
        line = TESLA_LINE.rsplit(",", 4)[0] + ",0,1,0,0"
        self.assertEqual(teslabms.parse_inventory_line(line)["faults"], 1)
        line = TESLA_LINE.rsplit(",", 4)[0] + ",0,20,0,0"
        module = teslabms.parse_inventory_line(line)
        self.assertEqual(module["faults"], 0x20)
        self.assertIn("registers inconsistent", module["flags"])

    def test_faulted_cells_are_named_from_the_bitmask(self):
        line = TESLA_LINE.rsplit(",", 4)[0] + ",0,1,5,0"
        module = teslabms.parse_inventory_line(line)
        self.assertIn("cell overvoltage", module["flags"])
        self.assertIn("overvoltage on cell 1, 3", module["flags"])

    def test_alerts_and_faults_are_separate_tables(self):
        line = TESLA_LINE.rsplit(",", 4)[0] + ",8,0,0,0"
        module = teslabms.parse_inventory_line(line)
        self.assertEqual(module["flags"], ["thermal shutdown"])

    def test_rejects_non_inv_and_short_lines(self):
        for bad in ("", "Starting up!", "INV,1,24.4", "INV-END"):
            with self.assertRaises(ValueError):
                teslabms.parse_inventory_line(bad)

    def test_block_parse_skips_chatter_and_sorts(self):
        lines = ["Starting up!", TESLA_LINE.replace("INV,1", "INV,3"),
                 TESLA_LINE, "", "some warning"]
        modules = teslabms.parse_inventory(lines)
        self.assertEqual([m["addr"] for m in modules], [1, 3])

    def test_bank_voltage_averages_parallel_modules(self):
        # The six modules are paralleled, so the bank sits at one module's
        # voltage -- summing them would report ~146 V for a 24 V bank.
        modules = teslabms.parse_inventory([TESLA_LINE, TESLA_LINE])
        pack = teslabms.summarise(modules)
        self.assertAlmostEqual(pack["voltage"], 24.4418, places=4)
        self.assertAlmostEqual(pack["series_sum_v"], 48.8836, places=4)
        self.assertEqual(pack["modules"], 2)
        self.assertFalse(pack["faulted"])
        self.assertAlmostEqual(pack["avg_cell"], 4.09238, places=5)

    def test_bank_soc_is_estimated_from_cell_voltage(self):
        pack = teslabms.summarise(teslabms.parse_inventory([TESLA_LINE]))
        # Cells at ~4.092 V, so high-80s -- and the charger is set to ~85%.
        self.assertAlmostEqual(pack["soc_estimate"], 87.7, delta=1.5)
        self.assertLessEqual(pack["soc_estimate_low"], pack["soc_estimate"])
        self.assertGreaterEqual(pack["soc_estimate_high"], pack["soc_estimate"])

    def test_each_module_carries_its_own_estimate(self):
        module = teslabms.parse_inventory_line(TESLA_LINE)
        self.assertAlmostEqual(module["soc_estimate"], 87.7, delta=1.5)

    def test_estimate_is_labelled_as_one(self):
        payload = teslabms.TeslaBMS._summarise(
            None, teslabms.parse_inventory([TESLA_LINE]),
            teslabms.summarise(teslabms.parse_inventory([TESLA_LINE])))
        labels = [s["label"] for s in payload["summary"]]
        self.assertIn("SOC (est)", labels)
        self.assertTrue(any("estimated" in n for n in payload["notes"]))

    def test_module_spread_is_the_paralleling_number(self):
        low = TESLA_LINE.replace("INV,1,24.4418", "INV,2,24.3918")
        pack = teslabms.summarise(teslabms.parse_inventory([TESLA_LINE, low]))
        self.assertAlmostEqual(pack["module_spread_v"], 0.05, places=4)
        self.assertAlmostEqual(pack["module_min"], 24.3918, places=4)
        self.assertAlmostEqual(pack["module_max"], 24.4418, places=4)

    def test_summary_of_nothing_is_empty_not_a_crash(self):
        self.assertEqual(teslabms.summarise([]), {})


# Frames captured from glorb's CAN bus on 2026-09-02.
ORION_A = bytes.fromhex("01900041131100AF")
ORION_B = bytes.fromhex("01900046141100B5")
PARALLEL_MUX0 = bytes.fromhex("0002DD001CA3ACA2")
PARALLEL_MUX1 = bytes.fromhex("010000019000412B")
PARALLEL_MUX2 = bytes.fromhex("0200301113000EBC")


class TestSocCurve(unittest.TestCase):
    def test_agrees_with_the_orions_own_soc_for_the_same_cells(self):
        # The one independent check available: on 2026-09-02 the Orion
        # reported 86% with the 72 V pack at 73.3 V / 18 series cells.
        self.assertAlmostEqual(soc.estimate_soc(73.3 / 18), 86.0, delta=1.0)

    def test_endpoints(self):
        self.assertEqual(soc.estimate_soc(4.20), 100.0)
        self.assertEqual(soc.estimate_soc(3.00), 0.0)
        self.assertEqual(soc.estimate_soc(4.25), 100.0)
        self.assertEqual(soc.estimate_soc(2.90), 0.0)

    def test_monotonic_across_the_whole_curve(self):
        previous = -1.0
        voltage = 3.00
        while voltage <= 4.20001:
            value = soc.estimate_soc(voltage)
            self.assertIsNotNone(value)
            self.assertGreaterEqual(value, previous)
            previous = value
            voltage += 0.005

    def test_interpolates_between_table_points(self):
        # Halfway between the 4.06 V/85% and 4.12 V/90% points.
        self.assertAlmostEqual(soc.estimate_soc(4.09), 87.5, places=4)

    def test_implausible_readings_return_nothing_rather_than_clamping(self):
        # A dead channel reading 0 V must not be reported as an empty cell.
        for bad in (0.0, 5.0, None, -1.0):
            self.assertIsNone(soc.estimate_soc(bad))


class TestOrion(unittest.TestCase):
    def test_checksum_accepts_captured_frames(self):
        for data in (ORION_A, ORION_B):
            self.assertTrue(orion.checksum_ok(orion.CAN_ID_STATUS, data))

    def test_checksum_rejects_a_corrupted_frame(self):
        bad = bytearray(ORION_A)
        bad[3] ^= 0x01
        self.assertFalse(orion.checksum_ok(orion.CAN_ID_STATUS, bytes(bad)))

    def test_checksum_rejects_wrong_length(self):
        self.assertFalse(orion.checksum_ok(orion.CAN_ID_STATUS, ORION_A[:6]))

    def test_status_decode(self):
        self.assertEqual(orion.parse_status(ORION_A),
                         {"dcl_a": 400, "ccl_a": 65,
                          "temp_high_c": 19, "temp_low_c": 17})
        self.assertEqual(orion.parse_status(ORION_B)["ccl_a"], 70)

    def test_parallel_mux0_carries_the_pack_voltage(self):
        fields = orion.parse_parallel(PARALLEL_MUX0)
        self.assertEqual(fields["bus_voltage"], 73.3)
        self.assertEqual(fields["relay_state"], 0)

    def test_soc_is_the_byte_that_complements_dod(self):
        # Reading these the wrong way round reports an 86%-charged pack as
        # 14%, which is what 73.3 V across 18 series cells rules out.
        fields = orion.parse_parallel(PARALLEL_MUX0)
        self.assertEqual(fields["soc"], 86.0)
        self.assertEqual(fields["dod"], 14.0)
        self.assertEqual(fields["soc"] + fields["dod"], 100.0)

    def test_soc_and_dod_stay_complementary_across_the_range(self):
        for raw_dod in (0, 40, 100, 150, 200):
            frame = bytearray(PARALLEL_MUX0)
            frame[4] = raw_dod
            frame[6] = 200 - raw_dod
            fields = orion.parse_parallel(bytes(frame))
            self.assertEqual(fields["soc"] + fields["dod"], 100.0)

    def test_second_soc_estimate_is_kept_separate(self):
        fields = orion.parse_parallel(PARALLEL_MUX0)
        self.assertEqual(fields["soc_alt"], 81.5)
        self.assertNotEqual(fields["soc_alt"], fields["soc"])

    def test_parallel_mux1_matches_the_per_unit_limits(self):
        fields = orion.parse_parallel(PARALLEL_MUX1)
        self.assertEqual(fields["avg_current"], 0.0)
        self.assertEqual(fields["dcl_a"], 400)
        self.assertEqual(fields["ccl_a"], 65)

    def test_parallel_mux2_matches_the_per_unit_temperatures(self):
        fields = orion.parse_parallel(PARALLEL_MUX2)
        self.assertEqual(fields["temp_low_c"], 17)
        self.assertEqual(fields["temp_high_c"], 19)

    def test_unknown_mux_yields_nothing_rather_than_guesses(self):
        self.assertEqual(orion.parse_parallel(bytes(8)[:0] + b"\x09" * 8), {})

    def test_current_is_signed(self):
        frame = bytearray(PARALLEL_MUX1)
        frame[1:3] = (-125).to_bytes(2, "big", signed=True)
        self.assertEqual(orion.parse_parallel(bytes(frame))["avg_current"],
                         -12.5)


class FakeCanPort:
    """Replays a scripted sequence of CAN frames, one batch per drain()."""

    def __init__(self, batches):
        self.batches = list(batches)
        self.opened = False
        self.closed = False

    def open(self):
        self.opened = True

    def drain(self):
        return self.batches.pop(0) if self.batches else []

    def close(self):
        self.closed = True


class TestOrionBus(unittest.TestCase):
    def _bus(self, batches, **kw):
        return orion.OrionBus(FakeCanPort(batches), settle_s=0.0, **kw)

    def test_both_units_are_separated_by_burst_position(self):
        batch = [
            (orion.CAN_ID_STATUS, ORION_A, False),
            (orion.CAN_ID_STATUS, ORION_B, False),
            (orion.CAN_ID_PARALLEL, PARALLEL_MUX0, True),
        ]
        payload, _ = self._bus([batch]).poll()
        names = [u["name"] for u in payload["units"]]
        self.assertEqual(names, ["Orion A", "Orion B"])
        self.assertEqual(payload["units"][0]["ccl_a"], 65)
        self.assertEqual(payload["units"][1]["ccl_a"], 70)
        self.assertEqual(payload["pack"]["bus_voltage"], 73.3)
        self.assertEqual(payload["state"], "ok")

    def test_a_whole_second_of_traffic_still_means_two_units(self):
        # One drained batch holds ~20 alternating frames. Before slot
        # assignment was bounded this reported "20 units on CAN".
        batch = []
        for _ in range(10):
            batch.append((orion.CAN_ID_STATUS, ORION_A, False))
            batch.append((orion.CAN_ID_STATUS, ORION_B, False))
        payload, _ = self._bus([batch]).poll()
        self.assertEqual(len(payload["units"]), 2)
        self.assertEqual(payload["units"][0]["ccl_a"], 65)
        self.assertEqual(payload["units"][1]["ccl_a"], 70)
        self.assertEqual([u["frames"] for u in payload["units"]], [10, 10])

    def test_a_dropped_frame_does_not_swap_the_units_forever(self):
        # Round-robin alone would flip phase after the missing B and report
        # unit A's readings under unit B's name from then on.
        batch = [(orion.CAN_ID_STATUS, ORION_A, False),
                 (orion.CAN_ID_STATUS, ORION_B, False),
                 (orion.CAN_ID_STATUS, ORION_A, False),
                 # B's frame is lost here
                 (orion.CAN_ID_STATUS, ORION_A, False),
                 (orion.CAN_ID_STATUS, ORION_B, False)]
        payload, _ = self._bus([batch]).poll()
        self.assertEqual(len(payload["units"]), 2)
        self.assertEqual(payload["units"][0]["ccl_a"], 65)
        self.assertEqual(payload["units"][1]["ccl_a"], 70)

    def test_identical_units_fall_back_to_alternation(self):
        # Nothing distinguishes them, so both slots must still be filled
        # rather than every frame collapsing onto one unit.
        batch = [(orion.CAN_ID_STATUS, ORION_A, False) for _ in range(6)]
        payload, _ = self._bus([batch]).poll()
        self.assertEqual(len(payload["units"]), 2)
        self.assertEqual(payload["state"], "ok")

    def test_slot_count_is_capped_by_expected_units(self):
        batch = [(orion.CAN_ID_STATUS, ORION_A, False),
                 (orion.CAN_ID_STATUS, ORION_B, False)]
        payload, _ = self._bus([batch], expected_units=1).poll()
        self.assertEqual(len(payload["units"]), 1)

    def test_one_unit_is_a_warning_not_a_success(self):
        batch = [(orion.CAN_ID_STATUS, ORION_A, False)]
        payload, _ = self._bus([batch]).poll()
        self.assertEqual(payload["state"], "warn")
        self.assertIn("1 of 2", payload["status_text"])

    def test_silent_bus_is_down(self):
        payload, _ = self._bus([[]]).poll()
        self.assertEqual(payload["state"], "down")
        self.assertEqual(payload["units"], [])

    def test_corrupted_frames_are_dropped_and_counted(self):
        bad = bytearray(ORION_A)
        bad[2] ^= 0xFF
        payload, _ = self._bus([[(orion.CAN_ID_STATUS, bytes(bad), False)]]).poll()
        self.assertEqual(payload["units"], [])
        self.assertTrue(any("checksum" in n for n in payload["notes"]))

    def test_unexpected_ids_are_reported_not_decoded(self):
        payload, _ = self._bus([[(0x123, bytes(8), False)]]).poll()
        self.assertTrue(any("0x123" in n for n in payload["notes"]))

    def test_summary_omits_fields_the_bus_never_sent(self):
        batch = [(orion.CAN_ID_STATUS, ORION_A, False),
                 (orion.CAN_ID_STATUS, ORION_B, False)]
        payload, _ = self._bus([batch]).poll()
        self.assertNotIn("Bus", [s["label"] for s in payload["summary"]])


class TestSlcan(unittest.TestCase):
    def test_standard_frame(self):
        self.assertEqual(slcan.parse_frame("t6B1801900041131100AF"),
                         (0x6B1, ORION_A, False))

    def test_extended_frame_with_this_firmwares_lowercase_prefix(self):
        self.assertEqual(slcan.parse_frame("x1850F3F380002DD001CA3ACA2"),
                         (0x1850F3F3, PARALLEL_MUX0, True))

    def test_uppercase_extended_prefix_also_works(self):
        self.assertEqual(slcan.parse_frame("T1850F3F380002DD001CA3ACA2")[0],
                         0x1850F3F3)

    def test_non_frame_lines_are_ignored(self):
        for line in ("", "V010403", "NC3948B2D", "\x06", "z999"):
            self.assertIsNone(slcan.parse_frame(line))

    def test_truncated_and_malformed_frames_are_ignored(self):
        for line in ("t6B18019000", "t6B1", "tZZZ8" + "0" * 16,
                     "t6B19" + "0" * 18):
            self.assertIsNone(slcan.parse_frame(line))

    def test_zero_length_frame(self):
        self.assertEqual(slcan.parse_frame("t1230"), (0x123, b"", False))

    def test_unsupported_bitrate_is_refused(self):
        with self.assertRaises(ValueError):
            slcan.SlcanPort(lambda **kw: None, bitrate=333_000)


class TestPorts(unittest.TestCase):
    def setUp(self):
        self._real = ports.discover
        ports.discover = lambda: {"12v": "COM8", "24v": "COM7", "72v": "COM4"}

    def tearDown(self):
        ports.discover = self._real

    def test_no_overrides_keeps_discovery(self):
        self.assertEqual(ports.resolve(None)["24v"], "COM7")

    def test_unspecified_override_is_not_a_disable(self):
        # argparse hands us None for a flag the user did not pass.
        resolved = ports.resolve({"12v": None, "24v": None, "72v": None})
        self.assertEqual(len(resolved), 3)

    def test_explicit_value_wins(self):
        self.assertEqual(ports.resolve({"24v": "COM9"})["24v"], "COM9")

    def test_empty_string_disables_a_system(self):
        self.assertNotIn("12v", ports.resolve({"12v": ""}))


class TestHubHelpers(unittest.TestCase):
    def test_busy_port_gets_an_actionable_message(self):
        import serial
        exc = serial.SerialException(
            "could not open port 'COM8': PermissionError(13, 'Access is denied.')")
        self.assertIn("another program", hub.explain(exc))

    def test_missing_adapter_is_explained(self):
        import serial
        exc = serial.SerialException("could not open port 'COM9'")
        self.assertIn("USB", hub.explain(exc))

    def test_other_errors_pass_through(self):
        self.assertEqual(hub.explain(ValueError("only 3 groups")),
                         "only 3 groups")

    def test_nameless_exception_still_says_something(self):
        self.assertEqual(hub.explain(TimeoutError()), "TimeoutError")


class TestHubSnapshot(unittest.TestCase):
    def test_snapshot_reports_every_configured_system(self):
        monitor = hub.Hub({"12v": "COM8", "72v": "COM4"})
        snap = monitor.snapshot()
        self.assertEqual(sorted(snap["systems"]), ["12v", "72v"])
        # Nothing has polled yet, so both are down and both raise an alert.
        self.assertEqual(len(snap["alerts"]), 2)

    def test_update_then_snapshot_is_ok_and_quiet(self):
        monitor = hub.Hub({"24v": "COM7"})
        monitor.update("24v", "COM7",
                       {"state": "ok", "status_text": "6 modules",
                        "summary": [], "modules": []}, ["i -> 6 lines"])
        snap = monitor.snapshot()
        self.assertEqual(snap["systems"]["24v"]["state"], "ok")
        self.assertEqual(snap["alerts"], [])
        self.assertLess(snap["systems"]["24v"]["age_s"], 5)
        self.assertEqual(monitor.raw()["24v"], ["i -> 6 lines"])

    def test_a_stale_reading_is_not_presented_as_current(self):
        monitor = hub.Hub({"24v": "COM7"})
        monitor.update("24v", "COM7",
                       {"state": "ok", "status_text": "6 modules",
                        "summary": []}, [])
        monitor._systems["24v"]["updated"] -= hub.STALE_AFTER_S + 5
        self.assertEqual(monitor.snapshot()["systems"]["24v"]["state"], "stale")

    def test_failure_keeps_the_system_visible(self):
        monitor = hub.Hub({"12v": "COM8"})
        import serial
        monitor.fail("12v", "COM8", serial.SerialException(
            "could not open port 'COM8': PermissionError(13, 'Access is denied.')"))
        system = monitor.snapshot()["systems"]["12v"]
        self.assertEqual(system["state"], "down")
        self.assertIn("another program", system["status_text"])
        self.assertEqual(system["summary"], [])

    def test_subscribers_receive_updates_and_can_leave(self):
        monitor = hub.Hub({"24v": "COM7"})
        q = monitor.subscribe()
        monitor.update("24v", "COM7",
                       {"state": "ok", "status_text": "", "summary": []}, [])
        self.assertEqual(q.get_nowait()["systems"]["24v"]["state"], "ok")
        monitor.unsubscribe(q)
        monitor.update("24v", "COM7",
                       {"state": "ok", "status_text": "", "summary": []}, [])
        self.assertTrue(q.empty())

    def test_a_stalled_subscriber_does_not_block_polling(self):
        monitor = hub.Hub({"24v": "COM7"})
        monitor.subscribe()          # never drained
        for _ in range(20):
            monitor.update("24v", "COM7",
                           {"state": "ok", "status_text": "", "summary": []}, [])


if __name__ == "__main__":
    unittest.main()
