/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2023 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <string.h>

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
CAN_HandleTypeDef hcan;

CRC_HandleTypeDef hcrc;

IWDG_HandleTypeDef hiwdg;

/* USER CODE BEGIN PV */

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_CAN_Init(void);
static void MX_CRC_Init(void);
static void MX_IWDG_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */


//-----------------------------------------------------------------------------
//  Defines
//-----------------------------------------------------------------------------


#define PAGE_SIZE 0x100 // Page size in words

//-----------------------------------------------------------------------------
//  Typedefs
//-----------------------------------------------------------------------------

struct bl_pvars_t // size has to be a multiple of 4
{
	uint32_t app_page_count;
	uint32_t app_crc;
};

struct __packed bl_cmd_t 
{
	uint8_t brd;
	uint8_t cmd;
	uint16_t par1;
	uint32_t par2;
};

_Static_assert (sizeof(struct bl_cmd_t) == 8);

//-----------------------------------------------------------------------------
// Constants
//-----------------------------------------------------------------------------

// CAN IDs for bootloader to respond to
static const uint16_t CANID_BOOTLOADER_CMD = 0xB0;
static const uint16_t CANID_BOOTLOADER_RPLY = 0xB1;

// Board ID for bootloader. Must be different for each board
static const uint8_t BL_BOARD_ID = 1;

// Magic value stored in memory - if this is present, skip bootloader and jump to app
static const uint32_t MAGIC_VAL = (uint32_t)(0x36051bf3);
static uint32_t* const MAGIC_ADDR = (uint32_t*)(SRAM_BASE + 0x1000);

// Base address to write app
static const uint32_t* APP_BASE = (uint32_t*)(0x08003000);
static const uint16_t PAGE_COUNT = 64 - 12;

// Bootloader commands
static const uint8_t BL_CMD_WRITE_BUF = 1; // Writes to the page buffer
static const uint8_t BL_CMD_WRITE_PAGE = 2; // Writes from the page buffer to flash (after verifying)
static const uint8_t BL_CMD_WRITE_CRC = 3; // Verify the entire program with a CRC
static const uint8_t BL_CMD_PING = 4; // Do nothing and respond

// How long the bootloader runs on startup if it doesn't receive a CAN message
// The main application will not run until this timeout expires
static const uint32_t STARTUP_TO = 200; // milliseconds
// 1 if a message has been received
uint8_t message_received = 0;

// Timeout after last CAN message to restart
static const uint32_t NOCANRX_TO = 2000; // milliseconds

//-----------------------------------------------------------------------------
//  Global variables
//-----------------------------------------------------------------------------

static volatile uint32_t lastcanrx;

//-----------------------------------------------------------------------------
//  utility functions
//-----------------------------------------------------------------------------

uint8_t __fls_wr(const uint32_t* page, const uint32_t* buf, uint32_t len)
{
  __HAL_FLASH_CLEAR_FLAG(FLASH_FLAG_EOP | FLASH_FLAG_PGERR | FLASH_FLAG_WRPERR);

  uint32_t erase_err;
  FLASH_EraseInitTypeDef erase_page = {
    FLASH_TYPEERASE_PAGES,
    FLASH_BANK_1,
    (uint32_t) page, 1
  };

	if( HAL_OK != HAL_FLASHEx_Erase(&erase_page, &erase_err) ) {
		return 1;
	}


	for(uint32_t i = 0; i < len; ++i ) {
		if( HAL_OK != HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD, (uint32_t)page, *buf) ) {
			return 2;
		}
		++page;
		++buf;
	}

	return 0;
}

uint8_t fls_wr(const uint32_t* page, const uint32_t* buf, uint32_t len)
{
	// does flash equal buffer already?
	if( 0 == memcmp(page, buf, 4*len) ) {
		return 0;
	}

	HAL_FLASH_Unlock();
	uint8_t r = __fls_wr(page, buf, len);
	HAL_FLASH_Lock();
	if( r ) {
		return r;
	}

  // verify
	if( 0 != memcmp(page, buf, 4*len) ) {
		return 10;
	}

	return 0;
}


void bl_tx_resp(uint8_t cmd, uint8_t ec)
{
	CAN_TxHeaderTypeDef m;
	m.IDE = CAN_ID_STD;
	m.StdId = CANID_BOOTLOADER_RPLY;
	m.RTR = CAN_RTR_DATA;
	m.DLC = 3;
  uint8_t data[3];
	data[0] = BL_BOARD_ID;
	data[1] = cmd;
	data[2] = ec;
  uint32_t mailbox;
	HAL_CAN_AddTxMessage(&hcan, &m, data, &mailbox);
  // Wait on TX message
  while(HAL_CAN_IsTxMessagePending(&hcan, mailbox));
}

// Runs before any other code. Checks for magic value in memory from before bootloader reset
// and jumps to the app if it's present.
void PreSystemInit(void)
{
  // Check for magic value
	if( *(MAGIC_ADDR) == MAGIC_VAL ) {
    // Magic value is present. Reset it then jump to app.
		*(MAGIC_ADDR) = 0;
		__set_MSP(*(APP_BASE));
		uint32_t app = *(APP_BASE + 1); // +1 = 4 bytes since uint32_t
		asm("bx %0\n"::"r" (app):);
	}
}

// //-----------------------------------------------------------------------------
// //  CAN msg processing
// //-----------------------------------------------------------------------------

void process_can_msg(CAN_RxHeaderTypeDef* msg, uint8_t data[])
{
	static uint32_t pagebuf[PAGE_SIZE];

	if( (msg->StdId == CANID_BOOTLOADER_CMD) && (msg->DLC == 8) ) {
		struct bl_cmd_t blc;
		memcpy(&blc, data, 8);
		if( blc.brd != BL_BOARD_ID ) return;
    message_received = 1;
		lastcanrx = HAL_GetTick();

    // ping command - just respond with OK
		if( blc.cmd == BL_CMD_PING ) {
      bl_tx_resp(blc.cmd, 0); // OK
			return;
		}

		// write buffer command, par1 = offset, par2 =data
		if( blc.cmd == BL_CMD_WRITE_BUF ) {
			if( blc.par1 < PAGE_SIZE ) {
				pagebuf[blc.par1] = blc.par2;
				bl_tx_resp(blc.cmd, 0); // OK
			} else {
				bl_tx_resp(blc.cmd, 1); // invalid ofs
			}
			return;
		}

		// write page command, par1 = page number, par2 = crc
		if( blc.cmd == BL_CMD_WRITE_PAGE ) {
			if( blc.par1 < PAGE_COUNT) {
        uint32_t crc = HAL_CRC_Calculate(&hcrc, pagebuf, PAGE_SIZE);
				if( crc == blc.par2 ) {
					uint32_t pgofs = blc.par1 * PAGE_SIZE;
					uint8_t r = fls_wr(APP_BASE + pgofs, pagebuf, PAGE_SIZE);
					if( r ) {
						bl_tx_resp(blc.cmd, 3); // verify failed
				  } else {
						bl_tx_resp(blc.cmd, 0); // OK
					}
				} else {
					bl_tx_resp(blc.cmd, 2); // invalid CRC
				}
			} else {
				bl_tx_resp(blc.cmd, 1); // invalid pagenum
			}
			return;
		}

		// write CRC command, par1 = number of pages, par2 = crc
		if( blc.cmd == BL_CMD_WRITE_CRC ) {
			if( blc.par1 <= PAGE_COUNT ) {
				__HAL_CRC_DR_RESET(&hcrc);

				uint32_t crc = HAL_CRC_Calculate(&hcrc, (uint32_t*)APP_BASE, blc.par1 * PAGE_SIZE);
				if( crc == blc.par2 ) {
					struct bl_pvars_t pv;
					pv.app_page_count = blc.par1;
					pv.app_crc = blc.par2;
					uint8_t r = fls_wr(APP_BASE - PAGE_SIZE, (uint32_t*)&pv, sizeof(pv)/4);
					if( r ) {
						bl_tx_resp(blc.cmd, 3); // verify failed
				  } else {
						bl_tx_resp(blc.cmd, 0); // OK
					}
				} else {
					bl_tx_resp(blc.cmd, 2); // invalid CRC
				}
			} else {
				bl_tx_resp(blc.cmd, 1); // invalid number of pages
			}
			return;
		}
	}
}

void can_irq(CAN_HandleTypeDef *pcan) {
  CAN_RxHeaderTypeDef msg;
  uint8_t data[8];
  HAL_CAN_GetRxMessage(pcan, CAN_RX_FIFO0, &msg, data);
  process_can_msg(&msg, data);
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{
  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_CAN_Init();
  MX_CRC_Init();
  MX_IWDG_Init();
  /* USER CODE BEGIN 2 */

  // if( SysTick_Config(SystemCoreClock / 1000) ) { // setup SysTick Timer for 1 msec interrupts
	// 	while( 1 );                                  // capture error
	// }

	// RCC_AHBPeriphClockCmd(RCC_AHBPeriph_CRC, ENABLE);

	// IWDG_WriteAccessCmd(IWDG_WriteAccess_Enable);
	// IWDG_SetPrescaler(IWDG_Prescaler_32); // approx 3s
	// IWDG_SetReload(0xfff);
	// IWDG_ReloadCounter();
	// IWDG_Enable();

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {

		// reset if no CAN messages received
    uint32_t timeout;
    if(message_received) timeout = NOCANRX_TO;
    else timeout=STARTUP_TO;

		if( HAL_GetTick() - lastcanrx > timeout ) {
			struct bl_pvars_t pv;
			memcpy(&pv, APP_BASE - PAGE_SIZE, sizeof(pv));

			if( (pv.app_page_count > 0) && (pv.app_page_count <= PAGE_COUNT) ) {
				// Check app CRC before jumping to the app
				uint32_t crc = HAL_CRC_Calculate(&hcrc, (uint32_t*)APP_BASE, pv.app_page_count * PAGE_SIZE);
				if( crc == pv.app_crc ) {
					*(MAGIC_ADDR) = MAGIC_VAL;
				}
			}
      // Reset the processor. If the magic value was set, the bootloader will be skipped, otherwise, the bootloader will restart.
			__NVIC_SystemReset();
		}

		// // feed watchdog
		HAL_IWDG_Refresh(&hiwdg);
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_LSI|RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.LSIState = RCC_LSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief CAN Initialization Function
  * @param None
  * @retval None
  */
static void MX_CAN_Init(void)
{

  /* USER CODE BEGIN CAN_Init 0 */

  /* USER CODE END CAN_Init 0 */

  /* USER CODE BEGIN CAN_Init 1 */

  /* USER CODE END CAN_Init 1 */
  hcan.Instance = CAN1;
  hcan.Init.Prescaler = 9;
  hcan.Init.Mode = CAN_MODE_NORMAL;
  hcan.Init.SyncJumpWidth = CAN_SJW_1TQ;
  hcan.Init.TimeSeg1 = CAN_BS1_6TQ;
  hcan.Init.TimeSeg2 = CAN_BS2_1TQ;
  hcan.Init.TimeTriggeredMode = DISABLE;
  hcan.Init.AutoBusOff = DISABLE;
  hcan.Init.AutoWakeUp = DISABLE;
  hcan.Init.AutoRetransmission = DISABLE;
  hcan.Init.ReceiveFifoLocked = DISABLE;
  hcan.Init.TransmitFifoPriority = DISABLE;
  if (HAL_CAN_Init(&hcan) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN CAN_Init 2 */
  // Accept all CAN messages
  CAN_FilterTypeDef sf;
  sf.FilterMaskIdHigh = 0x0000;
  sf.FilterMaskIdLow = 0x0000;
  sf.FilterFIFOAssignment = CAN_FILTER_FIFO0;
  sf.FilterBank = 0;
  sf.FilterMode = CAN_FILTERMODE_IDMASK;
  sf.FilterScale = CAN_FILTERSCALE_32BIT;
  sf.FilterActivation = CAN_FILTER_ENABLE;

  if (HAL_CAN_ConfigFilter(&hcan, &sf) != HAL_OK) {
    Error_Handler();
  }

  if (HAL_CAN_RegisterCallback(&hcan, HAL_CAN_RX_FIFO0_MSG_PENDING_CB_ID, can_irq)) {
    Error_Handler();
  }

  if (HAL_CAN_Start(&hcan) != HAL_OK) {
    Error_Handler();
  }

  if (HAL_CAN_ActivateNotification(&hcan, CAN_IT_RX_FIFO0_MSG_PENDING) != HAL_OK) {
    Error_Handler();
  }
  /* USER CODE END CAN_Init 2 */

}

/**
  * @brief CRC Initialization Function
  * @param None
  * @retval None
  */
static void MX_CRC_Init(void)
{

  /* USER CODE BEGIN CRC_Init 0 */

  /* USER CODE END CRC_Init 0 */

  /* USER CODE BEGIN CRC_Init 1 */

  /* USER CODE END CRC_Init 1 */
  hcrc.Instance = CRC;
  if (HAL_CRC_Init(&hcrc) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN CRC_Init 2 */

  /* USER CODE END CRC_Init 2 */

}

/**
  * @brief IWDG Initialization Function
  * @param None
  * @retval None
  */
static void MX_IWDG_Init(void)
{

  /* USER CODE BEGIN IWDG_Init 0 */

  /* USER CODE END IWDG_Init 0 */

  /* USER CODE BEGIN IWDG_Init 1 */

  /* USER CODE END IWDG_Init 1 */
  hiwdg.Instance = IWDG;
  hiwdg.Init.Prescaler = IWDG_PRESCALER_4;
  hiwdg.Init.Reload = 4095;
  if (HAL_IWDG_Init(&hiwdg) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN IWDG_Init 2 */

  /* USER CODE END IWDG_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
