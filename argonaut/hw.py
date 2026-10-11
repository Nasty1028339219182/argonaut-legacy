"""Hardware constants for Argonaut Legacy.

THOTH is a fantasy 32-bit RISC inspired by the published cycle budget of the
ARM720T-class core in the spec. It is not binary-compatible with ARM.
"""

CPU_HZ = 20_000_000
FRAME_HZ = 60
SCREEN_W = 320
SCREEN_H = 240
PIXELS = SCREEN_W * SCREEN_H
FB_BYTES = PIXELS * 2  # 153_600 = 150 KiB
PALETTE_SLOTS = 511  # indices 0..510
PIXEL_BUDGET = PIXELS  # blitter writes per frame after the free clear

SRAM_BASE = 0x00000000
SRAM_SIZE = 512 * 1024
AUDIO_BASE = 0x00060000
AUDIO_SIZE = 128 * 1024
STACK_TOP = AUDIO_BASE
HEAP_INIT = 0x00010000
GLOBALS_BASE = 0x00000200

HEAP_PTR = 0x00000080
FAULT_ADDR = 0x00000084
RNG_ADDR = 0x00000088
PRINT_LEN = 0x000000A0
PRINT_BUF = 0x000000A4
PRINT_MAX = 240

FB_BASE = 0x00100000
PAL_BASE = 0x00130000
PPU_BASE = 0x00140000
APU_BASE = 0x00150000
PAD_BASE = 0x00160000
SYS_BASE = 0x00170000
ROM_BASE = 0x02000000
ROM_SIZE = 8 * 1024 * 1024

# PPU register byte offsets
PPU_CMD = 0
PPU_COLOR = 4
PPU_X = 8
PPU_Y = 12
PPU_W = 16
PPU_H = 20
PPU_SRC = 24
PPU_SX = 28
PPU_SY = 32
PPU_CAMX = 36
PPU_CAMY = 40
PPU_STATUS = 44
PPU_PIXELS = 48

CMD_CLS = 1
CMD_PSET = 2
CMD_FILL = 3
CMD_BLIT = 4
CMD_SPR = 5
CMD_GLYPH = 6
CMD_MAP = 7
CMD_TEXT_STR = 8
CMD_TEXT_NUM = 9
CMD_PGET = 10
CMD_RECT = 11

# SYS
SYS_CYCLES = 0
SYS_FRAME = 4
SYS_LATE = 8
SYS_FAULT = 12
SYS_PALCLIP = 16
SYS_LOG = 20

# PAD
PAD_BTN = 0
PAD_EDGE = 4

# APU event ports (writes are events, not levels)
APU_SFX = 0x100
APU_MUSIC = 0x104

STR_MAGIC = 0x53545231  # STR1
LIST_MAGIC = 0x4C535431  # LST1

# Fault codes
FAULT_HEAP = 1
FAULT_DIV0 = 2
FAULT_INDEX = 3
FAULT_STACK = 4
FAULT_PRINT = 5
FAULT_FETCH = 6
FAULT_ROM_WRITE = 7
FAULT_ALIGN = 8

# Pad bits
BTN_LEFT = 0
BTN_RIGHT = 1
BTN_UP = 2
BTN_DOWN = 3
BTN_A = 4
BTN_B = 5
BTN_START = 6
BTN_SELECT = 7


def cycles_for_frame(index: int) -> int:
    """Guest cycles for a zero-based frame.

    20_000_000 / 60 = 333_333 + 1/3. Two frames of 333_333 and a third of
    333_334 sum to exactly 1_000_000 cycles every 3 frames.
    """
    if index % 3 == 2:
        return 333_334
    return 333_333


def s32(value: int) -> int:
    value &= 0xFFFFFFFF
    if value & 0x80000000:
        return value - 0x100000000
    return value
