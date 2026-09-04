"""Work out which COM port is which battery system.

The three adapters are different silicon, so USB VID:PID identifies them
without depending on COM numbering (which Windows reshuffles when things are
replugged into different USB sockets):

    2341:003D  Arduino Due programming port  -> 24 V TeslaBMS
    0403:6015  FTDI FT-X inside the CANdapter -> 72 V Orion pair
    1A86:7523  CH340 USB-RS485 dongle         -> 12 V EG4 pack

Any of these can be overridden from the command line when a spare adapter of
the same type gets pressed into service.
"""

from serial.tools import list_ports

# system id -> list of (vid, pid) that identify its adapter
SIGNATURES = {
    "24v": [(0x2341, 0x003D), (0x2341, 0x003E), (0x2A03, 0x003D)],
    "72v": [(0x0403, 0x6015), (0x0403, 0x6001), (0x0403, 0x6014)],
    "12v": [(0x1A86, 0x7523), (0x1A86, 0x5523), (0x1A86, 0x7522)],
}


def discover():
    """Map system id -> device name, for every adapter we can see.

    A system is simply absent from the result when its adapter is unplugged;
    when two adapters match the same signature the lowest-numbered port wins,
    which is stable enough to be predictable and can be overridden anyway.
    """
    found = {}
    for port in sorted(list_ports.comports(), key=lambda p: p.device):
        if port.vid is None or port.pid is None:
            continue
        for system, sigs in SIGNATURES.items():
            if (port.vid, port.pid) in sigs and system not in found:
                found[system] = port.device
    return found


def describe():
    """Every serial port present, for diagnostics when discovery comes up short."""
    out = []
    for port in sorted(list_ports.comports(), key=lambda p: p.device):
        vid = f"{port.vid:04X}" if port.vid is not None else "????"
        pid = f"{port.pid:04X}" if port.pid is not None else "????"
        out.append({
            "device": port.device,
            "description": port.description,
            "vid_pid": f"{vid}:{pid}",
        })
    return out


def resolve(overrides=None):
    """Discovered ports, with explicit overrides taking precedence.

    `overrides` maps system id -> device name. None means "not specified,
    use discovery"; an empty string disables that system entirely, so a flaky
    adapter can be taken out of the rotation without unplugging it.
    """
    ports = discover()
    for system, device in (overrides or {}).items():
        if device is None:
            continue
        if device:
            ports[system] = device
        else:
            ports.pop(system, None)
    return ports
