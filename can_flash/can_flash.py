import datetime
import sys
from sys import platform

import can
import crcmod as crcmod

PG_SIZE = 1024  # Page size in bytes
BL_WBUF = 1
BL_WPAGE = 2
BL_WCRC = 3
BL_PING = 4
CANID_BL_CMD = 0xb0
CANID_BL_RPL = 0xb1


# Create CAN message from id & data
def canmsg(id, data):
    if len(data) > 8:
        raise ValueError("invalid data")
    m = can.Message(arbitration_id=id, is_extended_id=False, data=data)
    return m


# Create bootloader CAN message
def bl_cmd(bus, board_id, cmd, par1, par2):
    # Create data for CAN message
    data = bytearray(8)
    data[0] = board_id
    data[1] = cmd
    data[2:4] = par1.to_bytes(2, 'little')
    data[4:8] = par2[::-1]

    bus.send(canmsg(CANID_BL_CMD, data), 0.5)


# Wait for a bootloader response
def bl_waitresp(bus, board_id, bl_cmd, timeout):
    absto = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
    while datetime.datetime.now() < absto:
        m = bus.recv(timeout)
        if m is not None:
            if (m.arbitration_id == CANID_BL_RPL) and (m.dlc >= 3) and (m.data[0] == board_id) and (m.data[1] == bl_cmd):
                return m.data[2]
    return None


def bl_cmd_response(bus, board_id, cmd, par1, par2, timeout_sec=1.0):
    bl_cmd(bus, board_id, cmd, par1, par2)
    r = bl_waitresp(bus, board_id, cmd, timeout_sec)
    if r is None:
        raise RuntimeError('Did not receive reply from board')
    if r > 0:
        raise RuntimeError(f'Bootloader command {cmd} error #{r}')
    return r


def bl_wait_for_connection(bus, board_id, timeout_sec=0.1, retries=10):
    for i in range(retries):
        # Ping bootloader
        bl_cmd(bus, board_id, BL_PING, 0, [0] * 4)
        # Wait for a response
        r = bl_waitresp(bus, board_id, BL_PING, timeout_sec)
        if r is not None:
            return True
    return False


# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # TODO Use Argparse
    if len(sys.argv) < 3:
        print("usage: prg.py board_id file.bin")
        sys.exit(0)

    board_id = int(sys.argv[1])

    bus = None
    if platform == "linux" or platform == "linux2" or platform == "darwin":
        # Stock slcan firmware on Linux (Assuming os x works the same?)
        bus = can.interface.Bus(bustype='slcan', channel='/dev/ttyACM1', bitrate=500000)
    elif platform == "win32":
        bus = can.interface.Bus(bustype='slcan', channel='COM0', bitrate=500000)

    if bus is None:
        print('Could not recognize OS to initialize CAN bus.')
        exit(1)

    # Read the program file
    filepath = sys.argv[2]
    # Check that the right file type is being uploaded
    if not filepath.endswith('.bin'):
        response = input('File path does not end in ".bin". Flash anyway? (Y/n): ')
        if 'n' in response.lower():
            print('Firmware flashing canceled')
            exit(0)

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
        print(f'Page {p}/{num_pages}', end='')
        # Start calculating page CRC
        pcrc = crcmod.Crc(0x104c11db7, initCrc=0xffffffff, rev=False)

        # Iterate over each 32-bit word of the page
        for w in range(PG_SIZE // 4):
            if w % 16 == 0:
                print('.', end='')

            # Get next data to send
            a = (p * PG_SIZE) + (w * 4)
            d = b[a:a + 4][::-1]  # take out 4 bytes and reverse them

            # update CRCs
            acrc.update(d)
            pcrc.update(d)

            # Send data and get response
            try:
                bl_cmd_response(bus, board_id, BL_WBUF, w, d)
            except RuntimeError as e:
                print(f'\nFirmware upload failed: {e}')
                exit(1)

        try:
            bl_cmd_response(bus, board_id, BL_WPAGE, p, pcrc.digest())
        except RuntimeError as e:
            print(f'\nPage verification failed: {e}')
            exit(1)

        print(" CRC OK")

    print('Verifying...')
    try:
        bl_cmd_response(bus, board_id, BL_WCRC, num_pages, acrc.digest())
    except RuntimeError:
        print('Verification failed')
        exit(1)

    print("Board flashed successfully")
