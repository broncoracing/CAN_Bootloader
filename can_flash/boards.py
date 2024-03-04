from pathlib import Path
from dataclasses import dataclass


@dataclass
class Board:
    board_id: int
    name: str
    fw_path: Path


# Firmwares for each bootloader ID
board_firmwares = [
    Board(1, 'BCM', Path('firmwares/bcm/firmware')),
    Board(2, 'Dashboard', Path('firmwares/dashboard/firmware')),
    # Board(2, 'telemetry', Path('firmwares/telemetry_firmware')),
    Board(10, 'Cell tap 0', Path('firmwares/cell-tap-connector-pcb/firmware')),
    Board(11, 'Cell tap 1', Path('firmwares/cell-tap-connector-pcb/firmware')),
    Board(12, 'Cell tap 2', Path('firmwares/cell-tap-connector-pcb/firmware')),
    Board(13, 'Cell tap 3', Path('firmwares/cell-tap-connector-pcb/firmware')),
    Board(14, 'Cell tap 4', Path('firmwares/cell-tap-connector-pcb/firmware')),
    Board(15, 'Cell tap 5', Path('firmwares/cell-tap-connector-pcb/firmware')),
    Board(16, 'Cell tap 6', Path('firmwares/cell-tap-connector-pcb/firmware')),
]

# For testing
# board_firmwares = [
#     Board(1, 'Test Board #1', Path('firmwares/board_1')),
#     Board(2, 'Test Board #2', Path('firmwares/board_2')),
# ]
