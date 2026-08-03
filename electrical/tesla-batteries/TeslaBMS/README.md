Arduino compatible project to interface with the BMS slave 
board on Tesla Model S modules.

## Local bare-Due bench configuration

This copy defaults to a bare Arduino Due connected to the Tesla UART through
the external level shifter. Optional CAN-gateway and external-I2C-EEPROM code
is disabled in `config.h`, so `due_can`, `can_common`, `due_wire`, and
`Wire_EEPROM` are not required. Automatic cell balancing and the unconnected
fault input are also disabled for initial bench testing. Settings remain in RAM
and return to defaults after reset.

Select **Arduino Due (Native USB Port)** in the Arduino IDE. The BMB serial bus
uses `Serial1`: Due D18/TX1 sends commands and D19/RX1 receives replies.

The modules are daisy-chained together with a TTL interface.
The interface uses a Molex 15-97-5101 connector and runs at
612500 baud. This can be a difficult baud rate to match with
arduino compatible processors. The Arduino Due and Teensy
3.5/3.6 boards are confirmed to be able to generate a suitably
close baud rate. The factory wiring to each module is comprised
of two sets of 5 differently colored wires:

* Red = 5V input to the module
* Green = Gnd for power and signal
* Gray = Fault output
* Yellow = UART Wire
* Blue = UART Wire

The fault output is active low. Use your own pull up to the fault line and if the line is pulled low then a fault has occurred.

Here is a PDF that explains how the wiring between modules and the master board is supposed to be:
https://cdn.hackaday.io/files/10098432032832/wiring.pdf
