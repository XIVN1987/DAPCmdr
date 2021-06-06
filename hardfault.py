import os


SCS_BASE  =  0xE000E000
SCB_BASE  = (SCS_BASE + 0x0D00)

SCB_CFSR  = (SCB_BASE + 0x28)   # Configurable Fault Status Register
SCB_HFSR  = (SCB_BASE + 0x2C)   # HardFault Status Register
SCB_DFSR  = (SCB_BASE + 0x30)   # Debug Fault Status Register
SCB_MFAR  = (SCB_BASE + 0x34)   # MemManage Fault Address Register
SCB_BFAR  = (SCB_BASE + 0x38)   # BusFault Address Register
SCB_AFSR  = (SCB_BASE + 0x3C)   # Auxiliary Fault Status Register

# HFSR: HardFault Status Register
SCB_HFSR_VECTTBL_Pos        =  1        # Indicates hard fault is caused by failed vector fetch
SCB_HFSR_VECTTBL_Msk        = (1 << SCB_HFSR_VECTTBL_Pos)
SCB_HFSR_FORCED_Pos         = 30        # Indicates hard fault is taken because of bus fault/memory management fault/usage fault
SCB_HFSR_FORCED_Msk         = (1 << SCB_HFSR_FORCED_Pos)
SCB_HFSR_DEBUGEVT_Pos       = 31        # Indicates hard fault is triggered by debug event
SCB_HFSR_DEBUGEVT_Msk       = (1 << SCB_HFSR_DEBUGEVT_Pos)

# MFSR: MemManage Fault Status Register
SCB_MFSR_IACCVIOL_Pos       = 0         # Instruction access violation
SCB_MFSR_IACCVIOL_Msk       = (1 << SCB_MFSR_IACCVIOL_Pos)
SCB_MFSR_DACCVIOL_Pos       = 1         # Data access violation
SCB_MFSR_DACCVIOL_Msk       = (1 << SCB_MFSR_DACCVIOL_Pos)
SCB_MFSR_MUNSTKERR_Pos      = 3         # Unstacking error
SCB_MFSR_MUNSTKERR_Msk      = (1 << SCB_MFSR_MUNSTKERR_Pos)
SCB_MFSR_MSTKERR_Pos        = 4         # Stacking error
SCB_MFSR_MSTKERR_Msk        = (1 << SCB_MFSR_MSTKERR_Pos)
SCB_MFSR_MMARVALID_Pos      = 7         # Indicates the MMAR is valid
SCB_MFSR_MMARVALID_Msk      = (1 << SCB_MFSR_MMARVALID_Pos)

# BFSR: Bus Fault Status Register
SCB_BFSR_IBUSERR_Pos        = 8         # Instruction access violation
SCB_BFSR_IBUSERR_Msk        = (1 << SCB_BFSR_IBUSERR_Pos)
SCB_BFSR_PRECISERR_Pos      = 9         # Precise data access violation
SCB_BFSR_PRECISERR_Msk      = (1 << SCB_BFSR_PRECISERR_Pos)
SCB_BFSR_IMPREISERR_Pos     = 10        # Imprecise data access violation
SCB_BFSR_IMPREISERR_Msk     = (1 << SCB_BFSR_IMPREISERR_Pos)
SCB_BFSR_UNSTKERR_Pos       = 11        # Unstacking error
SCB_BFSR_UNSTKERR_Msk       = (1 << SCB_BFSR_UNSTKERR_Pos)
SCB_BFSR_STKERR_Pos         = 12        # Stacking error
SCB_BFSR_STKERR_Msk         = (1 << SCB_BFSR_STKERR_Pos)
SCB_BFSR_BFARVALID_Pos      = 15        # Indicates BFAR is valid
SCB_BFSR_BFARVALID_Msk      = (1 << SCB_BFSR_BFARVALID_Pos)

# UFSR: Usage Fault Status Register
SCB_UFSR_UNDEFINSTR_Pos     = 16        # Attempts to execute an undefined instruction
SCB_UFSR_UNDEFINSTR_Msk     = (1 << SCB_UFSR_UNDEFINSTR_Pos)
SCB_UFSR_INVSTATE_Pos       = 17        # Attempts to switch to an invalid state (e.g., ARM)
SCB_UFSR_INVSTATE_Msk       = (1 << SCB_UFSR_INVSTATE_Pos)
SCB_UFSR_INVPC_Pos          = 18        # Attempts to do an exception with a bad value in the EXC_RETURN number
SCB_UFSR_INVPC_Msk          = (1 << SCB_UFSR_INVPC_Pos)
SCB_UFSR_NOCP_Pos           = 19        # Attempts to execute a coprocessor instruction
SCB_UFSR_NOCP_Msk           = (1 << SCB_UFSR_NOCP_Pos)
SCB_UFSR_UNALIGNED_Pos      = 24        # Indicates that an unaligned access fault has taken place
SCB_UFSR_UNALIGNED_Msk      = (1 << SCB_UFSR_UNALIGNED_Pos)
SCB_UFSR_DIVBYZERO0_Pos     = 25        # Indicates a divide by zero has taken place (can be set only if DIV_0_TRP is set)
SCB_UFSR_DIVBYZERO0_Msk     = (1 << SCB_UFSR_DIVBYZERO0_Pos)


def diagnosis(xlk):
    reg_HFSR = xlk.read_U32(SCB_HFSR)
    reg_CFSR = xlk.read_U32(SCB_CFSR)
    reg_MFAR = xlk.read_U32(SCB_MFAR)
    reg_BFAR = xlk.read_U32(SCB_BFAR)
    
    causes = []
    if reg_HFSR & SCB_HFSR_VECTTBL_Msk:
        causes.append('hard fault is caused by failed vector fetch')

    elif reg_HFSR & SCB_HFSR_FORCED_Msk:
        if reg_CFSR & (0xFF << 0):        # Memory Management Fault
            if reg_CFSR & SCB_MFSR_IACCVIOL_Msk:
                causes.append('Instruction access violation')

            if reg_CFSR & SCB_MFSR_DACCVIOL_Msk:
                causes.append('Data access violation')

            if reg_CFSR & SCB_MFSR_MUNSTKERR_Msk:
                causes.append('Unstacking error')

            if reg_CFSR & SCB_MFSR_MSTKERR_Msk:
                causes.append('Stacking error')

            if reg_CFSR & SCB_MFSR_MMARVALID_Msk:
                causes.append(f'SCB->MFAR = 0x{reg_MFAR:08X}')

        if reg_CFSR & (0xFF << 8):        # Bus Fault
            if reg_CFSR & SCB_BFSR_IBUSERR_Msk:
                causes.append('Instruction access violation')

            if reg_CFSR & SCB_BFSR_PRECISERR_Msk:
                causes.append('Precise data access violation')

            if reg_CFSR & SCB_BFSR_IMPREISERR_Msk:
                causes.append('Imprecise data access violation')

            if reg_CFSR & SCB_BFSR_UNSTKERR_Msk:
                causes.append('Unstacking error')

            if reg_CFSR & SCB_BFSR_STKERR_Msk:
                causes.append('Stacking error')

            if reg_CFSR & SCB_BFSR_BFARVALID_Msk:
                causes.append(f'SCB->BFAR = 0x{reg_BFAR:08X}')

        if reg_CFSR & (0xFFFF << 16):     # Usage Fault
            if reg_CFSR & SCB_UFSR_UNDEFINSTR_Msk:
                causes.append('Attempts to execute an undefined instruction')

            if reg_CFSR & SCB_UFSR_INVSTATE_Msk:
                causes.append('Attempts to switch to an invalid state (e.g., ARM)')

            if reg_CFSR & SCB_UFSR_INVPC_Msk:
                causes.append('Attempts to do an exception with a bad value in the EXC_RETURN number')

            if reg_CFSR & SCB_UFSR_NOCP_Msk:
                causes.append('Attempts to execute a coprocessor instruction')

            if reg_CFSR & SCB_UFSR_UNALIGNED_Msk:
                causes.append('an unaligned access fault has taken place')

            if reg_CFSR & SCB_UFSR_DIVBYZERO0_Msk:
                causes.append('a divide by zero has taken place (can be set only if DIV_0_TRP is set)')

    return causes
