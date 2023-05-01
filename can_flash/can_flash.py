import crcmod as crcmod
import argparse
import subprocess
import os
from colors import *
from boards import board_firmwares

from can_util import *

from sys import platform

PAGE_RETRIES = 10


def list_connected_boards(channel=None):
    print('Searching for connected boards...')
    bus = get_can_bus(channel)
    board_ids = bl_list_connected_boards(bus)
    if len(board_ids) == 0:
        print('No boards detected.')
    else:
        print(f'Detected the following boards:')
        for b_id in board_ids:
            matching_boards = list(filter(lambda b: b.board_id == b_id, board_firmwares))
            if len(matching_boards) > 0:
                print(f'  {b_id} {matching_boards[0].name}')
            else:
                print(f'  {b_id} Unknown board')

        if 0 in board_ids:
            print('\nAt least one board with ID 0 detected.\n'
                  'This board likely has a freshly programmed bootloader.\n'
                  'Be sure to set a proper ID before flashing these boards.')


# (try to) Flash a single page to the mcu
def flash_page(bus, board_id, page, pcrc, page_data):
    for w, d in page_data.items():
        if w % 16 == 0:
            print('.', end='')
        # Send data and get response
        bl_cmd_response(bus, board_id, BL_WBUF, w, d)

    bl_cmd_response(bus, board_id, BL_WPAGE, page, pcrc.digest())


# Flash an entire file to the mcu
def flash(board_id, filepath, channel=None, interactive=True):
    if interactive and not filepath.endswith('.bin'):
        response = input('File path does not end in ".bin". Flash anyway? (Y/n): ')
        if 'n' in response.lower():
            print('Firmware flashing canceled')
            exit(0)

    bus = get_can_bus(channel)

    f = open(filepath, "rb")
    b = bytearray(f.read())
    f.close()

    # Extend to the next whole page
    b.extend(bytearray(PG_SIZE - (len(b) % PG_SIZE)))
    num_pages = len(b) // PG_SIZE

    # App CRC
    acrc = crcmod.Crc(0x104c11db7, initCrc=0xffffffff, rev=False)

    # Reset & connect to board
    print(f'Attempting to connect to board with ID {board_id}')
    if not bl_wait_for_connection(bus, board_id):
        if interactive:
            print('Could not connect to board.')
            exit(1)
        else:
            raise RuntimeError('Could not connect to board.')

    print(f'Connected to board {board_id}. Uploading {filepath}')

    # TODO Ability to retry pages that failed
    for p in range(num_pages):
        print(f'Page {p}/{num_pages - 1}', end='')
        # Start calculating page CRC
        pcrc = crcmod.Crc(0x104c11db7, initCrc=0xffffffff, rev=False)

        # Iterate over each 32-bit word of the page
        # First generate CRCs and data
        page_data = {}
        for w in range(PG_SIZE // 4):
            # Get next data to send
            a = (p * PG_SIZE) + (w * 4)
            d = b[a:a + 4][::-1]  # take out 4 bytes and reverse them

            # update CRCs
            acrc.update(d)
            pcrc.update(d)

            page_data[w] = d

        page_success = False
        for i in range(PAGE_RETRIES):
            try:
                flash_page(bus, board_id, p, pcrc, page_data)
                print(" CRC OK")
                page_success = True
                break
            except RuntimeError as e:
                print('Error flashing page: ', e)
                print(f'Retrying Page {p}/{num_pages - 1}', end='')
        if not page_success:
            if interactive:
                print('Page write failed')
                exit(1)
            else:
                raise RuntimeError('Page write failed')

    print('Verifying...')
    try:
        bl_cmd_response(bus, board_id, BL_WCRC, num_pages, acrc.digest())
    except RuntimeError as e:
        if not interactive:
            raise e  # Just pass on the error
        else:
            print('Verification failed')
            exit(1)

    print("Board flashed successfully")


def multi_flash(clean=False, channel=None):
    # Check that firmware folders exist and build them
    for board in board_firmwares:
        print('\n\n')
        print(green(f'Building firmware for {board.name}'))
        if not board.fw_path.exists():
            print(f"Firmware folder {board.fw_path} does not exist! You may need to add it by initializing git "
                  f"submodules.")
            exit(1)

        
        if platform == 'win32':
            print(yellow('Unable to build firmware automatically on Windows. Do it manually through VSCode instead.'))
        else:
            # Clean build (if requested)
            if clean:
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

        print(f"Flashing binary {fw_binary_path} to board #{board.board_id}")
        flashed = False

        # Try up to 3 times to flash
        for _i in range(3):
            try:
                flash(board.board_id, fw_binary_path, channel=channel, interactive=False)
                flashed = True
                print(green(f'Successfully flashed {board.name}'))
                break
            except RuntimeError as e:
                print(yellow(f'Failed to flash board: {e}'))
        if not flashed:
            print(red(f'Failed to flash {board.name}.'))
            exit(1)


def change_id(board_id, new_id, channel=None):
    if new_id < 0 or new_id >= 255:
        print('Invalid ID. Choose an ID from 0-254.')
        exit(1)

    bus = get_can_bus(channel)

    print(f'Attempting to connect to board with ID {board_id}')
    if not bl_wait_for_connection(bus, board_id):
        print('Could not connect to board.')
        exit(1)
    print(f'Changing board ID {board_id} to {new_id}...')
    # Change ID
    bl_cmd(bus, board_id, BL_SET_ID, new_id, [0] * 4)
    r = bl_waitresp(bus, new_id, BL_SET_ID, timeout=1.0)
    if r is None:
        raise RuntimeError('Did not receive reply from board')
    if r > 0:
        raise RuntimeError(f'Bootloader command SET_ID returned error #{r}')

    print('Successfully changed board ID')


def flash_bl():
    if platform == 'win32':
        print('Unable to build/flash bootloader on Windows. Do it manually through VSCode instead.')
        return
    # Clean build to give a fresh build timestamp for the bootloader
    # This prevents new bootloaders from running old apps
    subprocess.run(('make', '-C', '../', '-f', 'STM32Make.make', 'clean'))
    # Build & flash MCU
    subprocess.run(('make', '-C', '../', '-f', 'STM32Make.make', 'flash', '-j4'))


def main():
    parser = argparse.ArgumentParser(description='CAN Bootloader flashing utility')
    parser.add_argument('-c', '--channel', type=str, help='Can channel (Defaults to /dev/ttyACM0 or COM0)',
                        required=False)

    subparsers = parser.add_subparsers(title='commands', dest='command')

    # Flash bootloader sub-parser
    flash_bl_parser = subparsers.add_parser('flash_bl', help='Flash bootloader to board')

    # Flash sub-parser
    flash_parser = subparsers.add_parser('flash', help='Flash a board')
    flash_parser.add_argument('-b', '--board', type=int, help='Integer input for board ID', required=True)
    flash_parser.add_argument('filepath', nargs='?', help='Path to the .bin file to be flashed')

    # Multi-flash sub-parser
    flash_all_parser = subparsers.add_parser('flash_all', help='Flash all known boards')
    flash_all_parser.add_argument('--clean', action='store_true',
                        help='Perform a clean build (Rebuild from scratch) on all firmwares')

    # Change ID sub-parser
    change_id_parser = subparsers.add_parser('change_id', help='Change the ID of a board')
    change_id_parser.add_argument('-b', '--board', type=int, help='Integer input for board ID', required=True)
    change_id_parser.add_argument('-i', '--id', type=int, help='new ID for the board', required=True)

    # List sub-parser
    list_parser = subparsers.add_parser('list', help='List connected boards')

    args = parser.parse_args()

    if args.command == 'flash':
        if args.filepath is None:
            print("Error: filepath is required for flash command")
            flash_parser.print_help()
            return
        flash(args.board, args.filepath, channel=args.channel)
    elif args.command == 'flash_bl':
        flash_bl()
    elif args.command == 'flash_all':
        multi_flash(clean=args.clean, channel=args.channel)
    elif args.command == 'change_id':
        change_id(args.board, args.id, channel=args.channel)
    elif args.command == 'list':
        list_connected_boards(channel=args.channel)
    else:
        parser.print_help()
        print()
        flash_parser.print_help()
        print()
        flash_all_parser.print_help()
        print()
        change_id_parser.print_help()


if __name__ == "__main__":
    main()
