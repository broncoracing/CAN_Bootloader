# CAN Bootloader
CANbus bootloader (Currently only for STM32F103 microcontrollers)
The bootloader lives in the first 12k of flash on the microcontroller, and runs every time the microcontroller resets or powers up.
Heavily inspired by https://github.com/matejx/stm32f1-CAN-bootloader/blob/master/prg.py, but using the STM32CubeMX HAL

## Usage
Build and flash the bootloader to the board. Make sure to set the `board_id` correctly!
Install the required python packages from `can_flash/requirements.txt`:
```bash
cd can_flash/
pip install -r requirements.txt
```
Run `can_flash/can_flash.py` to flash the firmware to the board:
```bash
python3 can_flash.py [board_id] [path/to/firmware.bin]
```

## Necessary application changes
The following changes must be made to the firmware to be able to flash it on a board with the CAN bootloader installed:
1. Modify linker script
  Replace the following line in `STM32F103C8Tx_FLASH.ld`:
  ```ld
  /*Before*/
  FLASH (rx)     : ORIGIN = 0x08000000, LENGTH = 64K
  /*After*/
  FLASH (rx)     : ORIGIN = 0x08003000, LENGTH = 52K
  ```
2. Add the following line to the user code 1 section of `main.c`:
  ```c
int main(void)
{
    /* USER CODE BEGIN 1 */
    // relocate vector table to work with bootloader
    SCB->VTOR = (uint32_t)0x08003000;
    /* USER CODE END 1 */
...
  ```
3. Make the application reset the MCU when a CAN frame with ID `0xB0` is received.
```c
...
switch (msg.StdId) {
    case 0xB0:
      __NVIC_SystemReset(); // Reset to bootloader
      break;
...
```
## Protocol
### The bootloader implements 4 commands:

    Write page buffer (BL_CMD_WRITE_BUF) is used to fill the bootloader's page buffer (in RAM) with data
    Write page (BL_CMD_WRITE_PAGE) is used to write the page buffer to flash
    Write CRC (BL_CMD_WRITE_CRC) is used to store entire flash CRC
    Ping (BL_CMD_PING) does nothing and replies, to verify that the bootloader is running.

### All 3 commands have the same format (8 bytes of standard CAN frame are used):

    uint8_t board ID
    uint8_t command
    uint16_t par1
    uint32_t par2

Each board appearing on the CAN bus should have a unique board ID. This assures you're actually talking to the board you want to be talking to.

### Write page buffer:

    offset (par1), offset into the page buffer
    data (par2), data to write at offset

### Write page:

    page number (par1), page number to flash with data in page buffer (0..PAGE_COUNT-1)
    page CRC (par2), page buffer CRC, if not matching, bootloader will not flash the page

### Write CRC:

    page count (par1), number of pages the firmware uses
    firmware CRC (par2), entire firmware CRC, if not matching the flash contents, bootloader will not flash firmware CRC

### To program the application firmware:

- Fill the entire page buffer 4 bytes at a time using several Write page buffer commands.
- Execute Write page command providing the correct page data CRC. The bootloader will compare your CRC to the CRC of its page buffer. If they match, it will flash the page.
- Repeat above steps for all pages.
- Finally execute Write CRC command providing the correct CRC for entire firmware. The bootloader will compare your CRC to the CRC of the MCU's flash. If they match, it will store the CRC in an unused page, allowing subsequent application execution.



