"""Unified monitoring for glorb's three battery systems.

12 V aux   -- 3x EG4 LifePower4, RS485 (CH340 adapter), polled request/response
24 V pack  -- Tesla modules via the TeslaBMS Arduino Due, USB serial console
72 V pack  -- 2x Orion BMS 2, listened to over CAN through an Ewert CANdapter

Everything here is read-only: the pollers send the minimum each protocol needs
to produce a reading and never write configuration.
"""

__version__ = "1.0.0"
