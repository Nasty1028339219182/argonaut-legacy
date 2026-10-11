"""Firmware that every cart is linked with. Written in THOTH assembly."""

from __future__ import annotations

from string import Template

from argonaut.hw import (
    AUDIO_BASE,
    CMD_CLS,
    CMD_FILL,
    CMD_MAP,
    CMD_PGET,
    CMD_PSET,
    CMD_RECT,
    CMD_SPR,
    CMD_TEXT_NUM,
    CMD_TEXT_STR,
    FAULT_ADDR,
    FAULT_DIV0,
    FAULT_HEAP,
    FAULT_INDEX,
    HEAP_INIT,
    HEAP_PTR,
    LIST_MAGIC,
    PPU_BASE,
    APU_BASE,
    APU_MUSIC,
    APU_SFX,
    PAD_BASE,
    PAL_BASE,
    RNG_ADDR,
    STACK_TOP,
    STR_MAGIC,
    SYS_BASE,
    SYS_CYCLES,
    SYS_FAULT,
    SYS_FRAME,
    SYS_LOG,
    SYS_PALCLIP,
    PPU_CAMX,
    PPU_CAMY,
    PPU_COLOR,
    PPU_H,
    PPU_SRC,
    PPU_SX,
    PPU_SY,
    PPU_W,
    PPU_X,
    PPU_Y,
)


def runtime_source() -> str:
    return Template(
        r"""
_start:
    LI SP, $stack_top
    ADDI FP, R0, 0
    LI R1, $heap_init
    LI R6, $heap_ptr
    STR R1, R6, 0
    LI R6, $fault_addr
    STR R0, R6, 0
    LI R1, 1
    LI R6, $rng_addr
    STR R1, R6, 0
    BL generated_init
_frame:
    BL user__update
    BL user__draw
    WFI
    B _frame

fn_cls:
    LUI R7, $ppu_hi
    STR R1, R7, $ppu_color
    ADDI R8, R0, $cmd_cls
    STR R8, R7, 0
    JR LR

fn_pset:
    LUI R7, $ppu_hi
    STR R1, R7, $ppu_x
    STR R2, R7, $ppu_y
    STR R3, R7, $ppu_color
    ADDI R8, R0, $cmd_pset
    STR R8, R7, 0
    JR LR

fn_pget:
    LUI R7, $ppu_hi
    STR R1, R7, $ppu_x
    STR R2, R7, $ppu_y
    ADDI R8, R0, $cmd_pget
    STR R8, R7, 0
    LDR R1, R7, $ppu_src
    JR LR

fn_rectfill:
    LUI R7, $ppu_hi
    STR R1, R7, $ppu_x
    STR R2, R7, $ppu_y
    STR R3, R7, $ppu_w
    STR R4, R7, $ppu_h
    STR R5, R7, $ppu_color
    ADDI R8, R0, $cmd_fill
    STR R8, R7, 0
    JR LR

fn_rect:
    LUI R7, $ppu_hi
    STR R1, R7, $ppu_x
    STR R2, R7, $ppu_y
    STR R3, R7, $ppu_w
    STR R4, R7, $ppu_h
    STR R5, R7, $ppu_color
    ADDI R8, R0, $cmd_rect
    STR R8, R7, 0
    JR LR

fn_spr:
    LUI R7, $ppu_hi
    STR R1, R7, $ppu_src
    STR R2, R7, $ppu_x
    STR R3, R7, $ppu_y
    STR R4, R7, $ppu_w
    STR R5, R7, $ppu_h
    ADDI R8, R0, $cmd_spr
    STR R8, R7, 0
    JR LR

fn_map:
    LUI R7, $ppu_hi
    STR R1, R7, $ppu_sx
    STR R2, R7, $ppu_sy
    STR R3, R7, $ppu_x
    STR R4, R7, $ppu_y
    STR R5, R7, $ppu_w
    STR R6, R7, $ppu_h
    ADDI R8, R0, $cmd_map
    STR R8, R7, 0
    JR LR

fn_camera:
    LUI R7, $ppu_hi
    STR R1, R7, $ppu_camx
    STR R2, R7, $ppu_camy
    JR LR

fn_text:
    PUSH LR
    PUSH R1
    PUSH R2
    PUSH R3
    PUSH R4
    CMP R1, R0
    BLE text_as_num
    ANDI R8, R1, 3
    CMP R8, R0
    BNE text_as_num
    LI R9, 65536
    CMP R1, R9
    BLT text_as_num
    LDR R8, R1, 0
    LI R9, $str_magic
    CMP R8, R9
    BNE text_as_num
    ADDI R6, R0, $cmd_text_str
    B text_go
text_as_num:
    ADDI R6, R0, $cmd_text_num
text_go:
    LDR R1, SP, 12
    LDR R2, SP, 8
    LDR R3, SP, 4
    LDR R4, SP, 0
    LUI R7, $ppu_hi
    STR R2, R7, $ppu_x
    STR R3, R7, $ppu_y
    STR R4, R7, $ppu_color
    STR R1, R7, $ppu_src
    STR R6, R7, 0
    ADDI SP, SP, 16
    POP LR
    JR LR

fn_btn:
    LUI R7, $pad_hi
    LDR R8, R7, 0
    SHR R8, R8, R1
    ANDI R1, R8, 1
    JR LR

fn_btnp:
    LUI R7, $pad_hi
    LDR R8, R7, 4
    SHR R8, R8, R1
    ANDI R1, R8, 1
    JR LR

fn_frame:
    LUI R7, $sys_hi
    LDR R1, R7, $sys_frame
    JR LR

fn_cycles:
    LUI R7, $sys_hi
    LDR R1, R7, $sys_cycles
    JR LR

fn_peek:
    LDR R1, R1, 0
    JR LR

fn_poke:
    STR R2, R1, 0
    JR LR

fn_log:
    LUI R7, $sys_hi
    STR R1, R7, $sys_log
    JR LR

fn_sfx:
    LUI R7, $apu_hi
    STR R1, R7, $apu_sfx
    JR LR

fn_music:
    LUI R7, $apu_hi
    STR R1, R7, $apu_music
    JR LR

fn_abs:
    CMP R1, R0
    BGE abs_ok
    SUB R1, R0, R1
abs_ok:
    JR LR

fn_min:
    CMP R1, R2
    BLE min_ok
    MOV R1, R2
min_ok:
    JR LR

fn_max:
    CMP R1, R2
    BGE max_ok
    MOV R1, R2
max_ok:
    JR LR

fn_pal:
    ADDI R6, R0, 511
    CMP R1, R6
    BGE pal_bad
    CMP R1, R0
    BLT pal_bad
    ANDI R2, R2, 31
    ANDI R3, R3, 31
    ANDI R4, R4, 31
    SHLI R2, R2, 10
    SHLI R3, R3, 5
    OR R2, R2, R3
    OR R2, R2, R4
    SHLI R1, R1, 1
    LUI R7, $pal_hi
    ADD R7, R7, R1
    STRH R2, R7, 0
    JR LR
pal_bad:
    LUI R7, $sys_hi
    LDR R8, R7, $sys_palclip
    ADDI R8, R8, 1
    STR R8, R7, $sys_palclip
    JR LR

fn_alloc:
    ADDI R1, R1, 3
    SHRI R1, R1, 2
    SHLI R1, R1, 2
    LI R6, $heap_ptr
    LDR R7, R6, 0
    ADD R8, R7, R1
    CMP R8, SP
    BLT alloc_ok
    LI R9, $fault_addr
    ADDI R10, R0, $fault_heap
    STR R10, R9, 0
    ADDI R1, R0, 0
    JR LR
alloc_ok:
    STR R8, R6, 0
    MOV R1, R7
    JR LR

fn_len:
    CMP R1, R0
    BLE len_zero
    LDR R2, R1, 0
    LI R3, $list_magic
    CMP R2, R3
    BNE len_zero
    LDR R1, R1, 4
    JR LR
len_zero:
    ADDI R1, R0, 0
    JR LR

fn_list_new:
    CMP R1, R0
    BGE list_new_ok
    ADDI R1, R0, 0
list_new_ok:
    PUSH LR
    PUSH R1
    SHLI R2, R1, 2
    ADDI R1, R2, 12
    BL fn_alloc
    CMP R1, R0
    BEQ list_new_fail
    LI R9, $list_magic
    STR R9, R1, 0
    LDR R2, SP, 0
    STR R2, R1, 4
    STR R2, R1, 8
    ADDI R10, R0, 0
    ADDI R11, R1, 12
list_zero:
    CMP R10, R2
    BGE list_new_done
    STR R0, R11, 0
    ADDI R11, R11, 4
    ADDI R10, R10, 1
    B list_zero
list_new_done:
    ADDI SP, SP, 4
    POP LR
    JR LR
list_new_fail:
    ADDI SP, SP, 4
    POP LR
    ADDI R1, R0, 0
    JR LR

fn_list_get:
    CMP R1, R0
    BLE list_bad
    LDR R3, R1, 0
    LI R4, $list_magic
    CMP R3, R4
    BNE list_bad
    LDR R3, R1, 4
    CMP R2, R0
    BLT list_bad
    CMP R2, R3
    BGE list_bad
    SHLI R2, R2, 2
    ADDI R1, R1, 12
    ADD R1, R1, R2
    LDR R1, R1, 0
    JR LR
list_bad:
    LI R7, $fault_addr
    ADDI R8, R0, $fault_index
    STR R8, R7, 0
    ADDI R1, R0, 0
    JR LR

fn_list_set:
    CMP R1, R0
    BLE list_bad
    LDR R6, R1, 0
    LI R4, $list_magic
    CMP R6, R4
    BNE list_bad
    LDR R6, R1, 4
    CMP R2, R0
    BLT list_bad
    CMP R2, R6
    BGE list_bad
    SHLI R2, R2, 2
    ADDI R1, R1, 12
    ADD R1, R1, R2
    STR R3, R1, 0
    JR LR

fn_floordiv:
    CMP R2, R0
    BEQ div_zero
    PUSH R0
    ADDI R6, R0, 0
    STR R6, SP, 0
    MOV R7, R1
    MOV R8, R2
    CMP R7, R0
    BGE div_apos
    ADDI R6, R0, 1
    STR R6, SP, 0
    SUB R7, R0, R7
div_apos:
    CMP R8, R0
    BGE div_bpos
    LDR R6, SP, 0
    XORI R6, R6, 1
    STR R6, SP, 0
    SUB R8, R0, R8
div_bpos:
    ADDI R9, R0, 0
    ADDI R10, R0, 0
    ADDI R11, R0, 31
div_bit:
    SHLI R10, R10, 1
    SHR R6, R7, R11
    ANDI R6, R6, 1
    OR R10, R10, R6
    CMP R10, R8
    BLTU div_nosub
    SUB R10, R10, R8
    ADDI R6, R0, 1
    SHL R6, R6, R11
    OR R9, R9, R6
div_nosub:
    ADDI R11, R11, -1
    CMP R11, R0
    BGE div_bit
    LDR R6, SP, 0
    CMP R6, R0
    BEQ div_same
    SUB R9, R0, R9
div_same:
    CMP R10, R0
    BEQ div_done
    CMP R6, R0
    BEQ div_done
    ADDI R9, R9, -1
div_done:
    MOV R1, R9
    ADDI SP, SP, 4
    JR LR
div_zero:
    LI R6, $fault_addr
    ADDI R7, R0, $fault_div0
    STR R7, R6, 0
    ADDI R1, R0, 0
    JR LR

fn_mod:
    PUSH LR
    PUSH R1
    PUSH R2
    BL fn_floordiv
    LDR R2, SP, 0
    MUL R3, R1, R2
    LDR R4, SP, 4
    SUB R1, R4, R3
    ADDI SP, SP, 8
    POP LR
    JR LR

fn_itoa:
    PUSH LR
    LI R6, 0x1B8
    STR R1, R6, 0
    LI R6, 0x1B4
    STR R0, R6, 0
    CMP R1, R0
    BGE itoa_pos
    ADDI R7, R0, 1
    STR R7, R6, 0
    SUB R1, R0, R1
    LI R6, 0x1B8
    STR R1, R6, 0
itoa_pos:
    LI R6, 0x1B8
    LDR R8, R6, 0
    CMP R8, R0
    BNE itoa_loop_start
    ADDI R1, R0, 9
    BL fn_alloc
    LI R9, $str_magic
    STR R9, R1, 0
    ADDI R9, R0, 1
    STR R9, R1, 4
    ADDI R9, R0, 48
    STRB R9, R1, 8
    POP LR
    JR LR
itoa_loop_start:
    ADDI R10, R0, 0
itoa_loop:
    LI R6, 0x1B8
    LDR R1, R6, 0
    ADDI R2, R0, 10
    PUSH R10
    BL fn_mod
    MOV R11, R1
    LI R6, 0x1B8
    LDR R1, R6, 0
    ADDI R2, R0, 10
    BL fn_floordiv
    LI R6, 0x1B8
    STR R1, R6, 0
    POP R10
    ADDI R11, R11, 48
    LI R6, 0x1C0
    ADD R6, R6, R10
    STRB R11, R6, 0
    ADDI R10, R10, 1
    LI R6, 0x1B8
    LDR R8, R6, 0
    CMP R8, R0
    BNE itoa_loop
    LI R6, 0x1B4
    LDR R9, R6, 0
    ADD R1, R10, R9
    ADDI R1, R1, 8
    PUSH R10
    PUSH R9
    BL fn_alloc
    POP R9
    POP R10
    CMP R1, R0
    BEQ itoa_fail
    LI R7, $str_magic
    STR R7, R1, 0
    ADD R7, R10, R9
    STR R7, R1, 4
    ADDI R8, R1, 8
    CMP R9, R0
    BEQ itoa_digits
    ADDI R7, R0, 45
    STRB R7, R8, 0
    ADDI R8, R8, 1
itoa_digits:
    ADDI R10, R10, -1
itoa_copy:
    CMP R10, R0
    BLT itoa_ret
    LI R6, 0x1C0
    ADD R6, R6, R10
    LDRB R7, R6, 0
    STRB R7, R8, 0
    ADDI R8, R8, 1
    ADDI R10, R10, -1
    B itoa_copy
itoa_ret:
    POP LR
    JR LR
itoa_fail:
    POP LR
    ADDI R1, R0, 0
    JR LR

fn_concat:
    PUSH LR
    PUSH R1
    PUSH R2
    MOV R1, R2
    BL is_str_r1
    MOV R11, R1
    LDR R1, SP, 4
    BL is_str_r1
    OR R10, R1, R11
    CMP R10, R0
    BNE concat_strings
    LDR R1, SP, 4
    LDR R2, SP, 0
    ADD R1, R1, R2
    ADDI SP, SP, 8
    POP LR
    JR LR
concat_strings:
    LDR R1, SP, 4
    BL coerce_str
    PUSH R1
    LDR R1, SP, 4
    BL coerce_str
    POP R2
    PUSH R2
    PUSH R1
    LDR R3, R2, 4
    LDR R4, R1, 4
    ADD R5, R3, R4
    PUSH R5
    ADDI R1, R5, 8
    BL fn_alloc
    POP R5
    POP R3
    POP R2
    CMP R1, R0
    BEQ concat_fail
    LI R7, $str_magic
    STR R7, R1, 0
    STR R5, R1, 4
    ADDI R8, R1, 8
    LDR R6, R2, 4
    ADDI R9, R2, 8
concat_c1:
    CMP R6, R0
    BLE concat_c2_init
    LDRB R7, R9, 0
    STRB R7, R8, 0
    ADDI R9, R9, 1
    ADDI R8, R8, 1
    ADDI R6, R6, -1
    B concat_c1
concat_c2_init:
    LDR R6, R3, 4
    ADDI R9, R3, 8
concat_c2:
    CMP R6, R0
    BLE concat_done
    LDRB R7, R9, 0
    STRB R7, R8, 0
    ADDI R9, R9, 1
    ADDI R8, R8, 1
    ADDI R6, R6, -1
    B concat_c2
concat_done:
    ADDI SP, SP, 8
    POP LR
    JR LR
concat_fail:
    ADDI SP, SP, 8
    POP LR
    ADDI R1, R0, 0
    JR LR

is_str_r1:
    CMP R1, R0
    BLE is_str_no
    ANDI R2, R1, 3
    CMP R2, R0
    BNE is_str_no
    LI R3, 65536
    CMP R1, R3
    BLT is_str_no
    LDR R2, R1, 0
    LI R3, $str_magic
    CMP R2, R3
    BNE is_str_no
    ADDI R1, R0, 1
    JR LR
is_str_no:
    ADDI R1, R0, 0
    JR LR

coerce_str:
    PUSH LR
    PUSH R1
    BL is_str_r1
    CMP R1, R0
    BEQ coerce_num
    POP R1
    POP LR
    JR LR
coerce_num:
    POP R1
    BL fn_itoa
    POP LR
    JR LR

fn_rnd:
    PUSH LR
    PUSH R1
    CMP R1, R0
    BLE rnd_zero
    LI R6, $rng_addr
    LDR R7, R6, 0
    SHLI R8, R7, 13
    XOR R7, R7, R8
    SHRI R8, R7, 17
    XOR R7, R7, R8
    SHLI R8, R7, 5
    XOR R7, R7, R8
    STR R7, R6, 0
    SHLI R1, R7, 1
    SHRI R1, R1, 1
    LDR R2, SP, 0
    BL fn_mod
    ADDI SP, SP, 4
    POP LR
    JR LR
rnd_zero:
    ADDI SP, SP, 4
    POP LR
    ADDI R1, R0, 0
    JR LR
"""
    ).substitute(
        stack_top=STACK_TOP,
        heap_init=HEAP_INIT,
        heap_ptr=HEAP_PTR,
        fault_addr=SYS_BASE + SYS_FAULT,
        rng_addr=RNG_ADDR,
        ppu_hi=PPU_BASE >> 16,
        pad_hi=PAD_BASE >> 16,
        sys_hi=SYS_BASE >> 16,
        apu_hi=APU_BASE >> 16,
        pal_hi=PAL_BASE >> 16,
        ppu_color=PPU_COLOR,
        ppu_x=PPU_X,
        ppu_y=PPU_Y,
        ppu_w=PPU_W,
        ppu_h=PPU_H,
        ppu_src=PPU_SRC,
        ppu_sx=PPU_SX,
        ppu_sy=PPU_SY,
        ppu_camx=PPU_CAMX,
        ppu_camy=PPU_CAMY,
        sys_frame=SYS_FRAME,
        sys_cycles=SYS_CYCLES,
        sys_log=SYS_LOG,
        sys_palclip=SYS_PALCLIP,
        apu_sfx=APU_SFX,
        apu_music=APU_MUSIC,
        cmd_cls=CMD_CLS,
        cmd_pset=CMD_PSET,
        cmd_pget=CMD_PGET,
        cmd_fill=CMD_FILL,
        cmd_rect=CMD_RECT,
        cmd_spr=CMD_SPR,
        cmd_map=CMD_MAP,
        cmd_text_str=CMD_TEXT_STR,
        cmd_text_num=CMD_TEXT_NUM,
        str_magic=STR_MAGIC,
        list_magic=LIST_MAGIC,
        fault_heap=FAULT_HEAP,
        fault_div0=FAULT_DIV0,
        fault_index=FAULT_INDEX,
    )
