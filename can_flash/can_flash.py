import crcmod as crcmod
import argparse

from can_util import *

PAGE_RETRIES=10

def list_connected_boards():
    print('Searching for connected boards...')
    bus = get_can_bus()
    boards = bl_list_connected_boards(bus)
    if len(boards) == 0:
        print('No boards detected.')
    else:
        print(f'Detected boards with the following IDs: {boards}')
        if 0 in boards:
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
def flash(board_id, filepath):
    if not filepath.endswith('.bin'):
        response = input('File path does not end in ".bin". Flash anyway? (Y/n): ')
        if 'n' in response.lower():
            print('Firmware flashing canceled')
            exit(0)

    bus = get_can_bus()

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
        print('Could not connect to board.')
        exit(1)

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
            print('Page write failed')
            exit(1)

    print('Verifying...')
    try:
        bl_cmd_response(bus, board_id, BL_WCRC, num_pages, acrc.digest())
    except RuntimeError:
        print('Verification failed')
        exit(1)

    print("Board flashed successfully")


def change_id(board_id, new_id):
    if new_id < 0 or new_id >= 255:
        print('Invalid ID. Choose an ID from 0-254.')
        exit(1)

    bus = get_can_bus()

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


def main():
    parser = argparse.ArgumentParser(description='CAN Bootloader flashing utility')
    subparsers = parser.add_subparsers(title='commands', dest='command')

    # Flash sub-parser
    flash_parser = subparsers.add_parser('flash', help='Flash a board')
    flash_parser.add_argument('-b', '--board', type=int, help='Integer input for board ID', required=True)
    flash_parser.add_argument('filepath', nargs='?', help='Path to the .bin file to be flashed')

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
        flash(args.board, args.filepath)
    elif args.command == 'change_id':
        change_id(args.board, args.id)
    elif args.command == 'list':
        list_connected_boards()
    else:
        parser.print_help()
        print()
        flash_parser.print_help()
        print()
        change_id_parser.print_help()


if __name__ == "__main__":
    main()
