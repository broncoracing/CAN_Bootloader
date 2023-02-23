import datetime
from sys import platform

import can

PG_SIZE = 1024  # Page size in bytes

# Bootloader commands
BL_WBUF = 1
BL_WPAGE = 2
BL_WCRC = 3
BL_PING = 4
BL_SET_ID = 5

# Bootload CAN IDs
CANID_BL_CMD = 0x700
CANID_BL_RPL_BASE = 0x701


# Check whether a message is a bootloader response
def is_bl_response_id(id):
    return 0 <= id - CANID_BL_RPL_BASE <= 254


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

    bus.send(canmsg(CANID_BL_CMD, data), 1.0)


# Wait for a bootloader response
def bl_waitresp(bus, board_id, bl_cmd, timeout):
    absto = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
    while datetime.datetime.now() < absto:
        m = bus.recv(timeout)
        if m is not None:
            if (is_bl_response_id(m.arbitration_id)) and (m.dlc >= 3) and (m.data[0] == board_id) and (m.data[1] == bl_cmd):
                return m.data[2]
    return None


def bl_cmd_response(bus, board_id, cmd, par1, par2, timeout_sec=0.05, retries=10):
    if retries == 0:
        raise RuntimeError('Did not receive reply from board')
    bl_cmd(bus, board_id, cmd, par1, par2)
    r = bl_waitresp(bus, board_id, cmd, timeout_sec)
    if r is None:
        return bl_cmd_response(bus, board_id, cmd, par1, par2, timeout_sec, retries - 1)
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


def bl_list_connected_boards(bus, timeout_sec=0.1, retries=10):
    board_ids = set()
    for i in range(retries):
        # Ping bootloader
        bl_cmd(bus, 0, BL_PING, 0, [0] * 4)
        absto = datetime.datetime.now() + datetime.timedelta(seconds=timeout_sec)
        while datetime.datetime.now() < absto:
            m = bus.recv(timeout_sec)
            if m is not None:
                # print(m.arbitration_id, m.data[1])
                if (is_bl_response_id(m.arbitration_id)) and (m.dlc >= 3) and (m.data[1] == BL_PING):
                    board_id = m.data[0]
                    board_ids.add(board_id)
    return board_ids


def get_can_bus():
    bus = None
    if platform == "linux" or platform == "linux2" or platform == "darwin":
        # Stock slcan firmware on Linux (Assuming os x works the same?)
        bus = can.interface.Bus(bustype='slcan', channel='/dev/ttyACM0', bitrate=500000)
    elif platform == "win32":
        bus = can.interface.Bus(bustype='slcan', channel='COM0', bitrate=500000)

    if bus is None:
        raise RuntimeError('Could not initialize CAN bus: OS not recognized')
    return bus
