from pathlib import Path
from dataclasses import dataclass


@dataclass
class Board:
    id: int
    name: str
    fw_path: Path


# Firmwares for each bootloader ID
board_firmwares = [
    Board(1, 'Test Board #1', Path('firmwares/board_1')),
    Board(2, 'Test Board #2', Path('firmwares/board_2')),
]

# board_firmwares = [
#     Board(1, 'BCM', Path('firmwares/bcm')),
#     Board(2, 'Dashboard', Path('firmwares/dashboard')),
#     # Board(2, 'telemetry', Path('firmwares/telemetry_firmware')),
# ]
