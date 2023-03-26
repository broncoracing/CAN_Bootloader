import can_flash
import argparse
import subprocess
import os
from colors import *
from boards import board_firmwares


def main():
    parser = argparse.ArgumentParser(description='CAN Bootloader multi-flashing utility')
    parser.add_argument('-c', '--channel', type=str, help='Can channel (Defaults to /dev/ttyACM0 or COM0)',
                        required=False)

    parser.add_argument('--clean', action='store_true',
                        help='Perform a clean build (Rebuild from scratch) on all firmwares')

    args = parser.parse_args()

    # Check that firmware folders exist and build them
    for board in board_firmwares:
        print('\n\n')
        print(green(f'Building firmware for {board.name}'))
        if not board.fw_path.exists():
            print(f"Firmware folder {board.fw_path} does not exist! You may need to add it by initializing git "
                  f"submodules.")
            exit(1)

        # Clean build (if requested)
        if args.clean:
            clean_res = subprocess.run(('make', '-f', 'STM32Make.make', '-C', board.fw_path, 'clean'))
            if clean_res != 0:
                print(yellow(f"Error while cleaning {board.fw_path}. That's kinda weird."))
                # Clean failing is not fatal ...
                # exit(2)

        # build the firmware
        build_res = subprocess.run(
            ('make', '-f', 'STM32Make.make', '-C', board.fw_path, '-j', '4'),
            stdout=open(os.devnull, 'wb')
        )

        if build_res.returncode != 0:
            print(red(f"Error while building {board.fw_path}. Exiting"))
            exit(3)

        fw_binary_path = board.fw_path / 'build' / 'firmware.bin'

        if not fw_binary_path.exists():
            print(red(f'Could not find firmware binary at {fw_binary_path}.'))
            exit(4)

        print(f"Flashing binary {fw_binary_path} to board #{board.id}")
        flashed = False

        # Try up to 3 times to flash
        for _i in range(3):
            try:
                can_flash.flash(board.id, fw_binary_path, channel=args.channel, interactive=False)
                flashed = True
                print(green(f'Successfully flashed {board.name}'))
                break
            except RuntimeError as e:
                print(red(f'Failed to flash board: {e}'))
        if not flashed:
            print(red(f'Failed to flash {board.name}.'))
            exit(1)


if __name__ == '__main__':
    main()
