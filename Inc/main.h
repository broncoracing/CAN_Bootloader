/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.h
  * @brief          : Header for main.c file.
  *                   This file contains the common defines of the application.
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

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "stm32f1xx_hal.h"
#include <string.h>
#include "version.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* USER CODE BEGIN EC */

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

/* Exported functions prototypes ---------------------------------------------*/
void Error_Handler(void);

/* USER CODE BEGIN EFP */

/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/

/* USER CODE BEGIN Private defines */
//-----------------------------------------------------------------------------
//  Defines
//-----------------------------------------------------------------------------


#define PAGE_SIZE 0x100 // Page size in words
#define BUILD_TIMESTAMP UNIX_TIMESTAMP //timestamp for when the bootloader was built. 

//-----------------------------------------------------------------------------
//  Typedefs
//-----------------------------------------------------------------------------

struct app_vars_t
{
  // Application binary size
  uint32_t page_count;
  // CRC of application to verify before jumping to it
	uint32_t crc;
};

struct board_vars_t
{
  // Timestamp from bootloader build. Used to reset data when flashing new bootloader.
  uint64_t bl_build_version;
  // Board ID for bootloader. Must be different for each board
  uint8_t id;
  uint8_t _padding[3];
};


struct bl_vars_t // size has to be a multiple of 4
{
  struct app_vars_t app;
  struct board_vars_t board;
};

_Static_assert(sizeof(struct bl_vars_t) % 4 == 0);

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

// Magic value stored in memory - if this is present, skip bootloader and jump to app
static const uint32_t MAGIC_VAL = (uint32_t)(0x36051bf3);
static uint32_t* const MAGIC_ADDR = (uint32_t*)(SRAM_BASE + 0x1000);

// Base address to write app
#define APP_BASE ((uint32_t *)(0x08003000))
#define PAGE_COUNT (64 - 12)
// static const uint32_t* APP_BASE = (uint32_t*)(0x08003000);
// static const uint16_t PAGE_COUNT = 64 - 12;

// Location where pvars are stored
#define FLASH_VARS ((volatile struct bl_vars_t *)(APP_BASE - PAGE_SIZE))


// Bootloader commands
static const uint8_t BL_CMD_WRITE_BUF = 1; // Writes to the page buffer
static const uint8_t BL_CMD_WRITE_PAGE = 2; // Writes from the page buffer to flash (after verifying)
static const uint8_t BL_CMD_WRITE_CRC = 3; // Verify the entire program with a CRC
static const uint8_t BL_CMD_PING = 4; // Do nothing and respond
static const uint8_t BL_CMD_SET_ID = 5; // Update the board's ID

// Bootloader error codes
static const uint8_t BL_SUCCESS = 0;
static const uint8_t BL_ERR_INVALID_PAGE_NUM = 1;
static const uint8_t BL_ERR_INVALID_CRC = 2;
static const uint8_t BL_ERR_FLASH_WRITE = 3;
static const uint8_t BL_ERR_INVALID_ID = 4;
static const uint8_t BL_ERR_INVALID_OFFSET = 5;

// How long the bootloader runs on startup if it doesn't receive a CAN message
// The main application will not run until this timeout expires
static const uint32_t STARTUP_TO = 200; // milliseconds

// Timeout after last CAN message to restart
static const uint32_t NOCANRX_TO = 2000; // milliseconds


/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
