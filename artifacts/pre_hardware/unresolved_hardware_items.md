# Unresolved hardware items

All entries below are `TODO(HW_VERIFY)` and remain unverified because no board or instrument was connected.

| Item | Required input | Verification method |
|---|---|---|
| A1/A2/T1/T2 board identity | J-Link serial IDs and physical labels | discovery result matched to one board at a time |
| UART mapping | four serial ports and firmware baud | identity record on each isolated port |
| Trace GPIOs | board-safe pin mapping | schematic review, firmware config, continuity check |
| Logic analyzer | device ID, channels, sample rate, voltage threshold | connection checklist and short smoke capture |
| SPI | clock target and waveform | config readback plus analyzer waveform |
| IRQ/ISR | DW IRQ pin and enabled interrupt path | assertion-to-ISR trace |
| CIR ownership | accumulator lifetime across RX events | controlled capture before/after next RX |
| Processing times | IRQ/SPI/UART/CIR/phase/filter endpoints | real logic capture with defined events |
| Antenna geometry | reference distances, height, orientation, photos | independent physical measurement record |
| Antenna-delay model | target nodes and identifiability constraints | repeated multi-distance collection and residual review |
| A1/A2/T1/T2 firmware | clean SDK, role targets, images, hashes | reproducible build before any flash |
| Actual 2A2T RF behavior | protocol/address/schedule implementation | staged 1A1T -> 2A1T -> 2A2T HIL tests |

`hardware_verified = false`
