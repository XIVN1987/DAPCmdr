"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2006-2015 ARM Limited
"""
import time
import logging

from ..pyDAPAccess import DAPAccess

# CPUID ARCHITECTURE values
ARMv6M = 0xC
ARMv7M = 0xF

# CPUID PARTNO values
ARM_CortexM0  = 0xC20
ARM_CortexM1  = 0xC21
ARM_CortexM3  = 0xC23
ARM_CortexM4  = 0xC24
ARM_CortexM0p = 0xC60

# User-friendly names for core types.
CORE_TYPE_NAME = {
    ARM_CortexM0  : "Cortex-M0",
    ARM_CortexM1  : "Cortex-M1",
    ARM_CortexM3  : "Cortex-M3",
    ARM_CortexM4  : "Cortex-M4",
    ARM_CortexM0p : "Cortex-M0+"
}

# Map from register name to DCRSR register index.
#
# The CONTROL, FAULTMASK, BASEPRI, and PRIMASK registers are special in that they share the
# same DCRSR register index and are returned as a single value. In this dict, these registers
# have negative values to signal to the register read/write functions that special handling
# is necessary. The values are the byte number containing the register value, plus 1 and then
# negated. So -1 means a mask of 0xff, -2 is 0xff00, and so on. The actual DCRSR register index
# for these combined registers has the key of 'cfbp'.
CORE_REGISTER = {
    'r0'  : 0,
    'r1'  : 1,
    'r2'  : 2,
    'r3'  : 3,
    'r4'  : 4,
    'r5'  : 5,
    'r6'  : 6,
    'r7'  : 7,
    'r8'  : 8,
    'r9'  : 9,
    'r10' : 10,
    'r11' : 11,
    'r12' : 12,
    'sp'  : 13,
    'r13' : 13,
    'lr'  : 14,
    'r14' : 14,
    'pc'  : 15,
    'r15' : 15,
    'xpsr': 16,
    'msp' : 17,
    'psp' : 18,
    'cfbp': 20,
    'control'  :-4,
    'faultmask':-3,
    'basepri'  :-2,
    'primask'  :-1,
    'fpscr': 33,
    's0' : 0x40,
    's1' : 0x41,
    's2' : 0x42,
    's3' : 0x43,
    's4' : 0x44,
    's5' : 0x45,
    's6' : 0x46,
    's7' : 0x47,
    's8' : 0x48,
    's9' : 0x49,
    's10': 0x4a,
    's11': 0x4b,
    's12': 0x4c,
    's13': 0x4d,
    's14': 0x4e,
    's15': 0x4f,
    's16': 0x50,
    's17': 0x51,
    's18': 0x52,
    's19': 0x53,
    's20': 0x54,
    's21': 0x55,
    's22': 0x56,
    's23': 0x57,
    's24': 0x58,
    's25': 0x59,
    's26': 0x5a,
    's27': 0x5b,
    's28': 0x5c,
    's29': 0x5d,
    's30': 0x5e,
    's31': 0x5f,
}

class CortexM(object):
    """
    This class has basic functions to access a Cortex M core:
       - init
       - read/write memory
       - read/write core registers
    """
    TARGET_RUNNING = 1   # Core is executing code.
    TARGET_HALTED = 2    # Core is halted in debug mode.
    TARGET_RESET = 3     # Core is being held in reset.
    TARGET_SLEEPING = 4  # Core is sleeping due to a wfi or wfe instruction.
    TARGET_LOCKUP = 5    # Core is locked up.

    # CPUID Register
    CPUID = 0xE000ED00
    CPUID_IMPLEMENTER_MASK  = 0xff000000
    CPUID_IMPLEMENTER_POS   = 24
    CPUID_IMPLEMENTER_ARM = 0x41
    CPUID_VARIANT_MASK      = 0x00f00000
    CPUID_VARIANT_POS       = 20
    CPUID_ARCHITECTURE_MASK = 0x000f0000
    CPUID_ARCHITECTURE_POS  = 16
    CPUID_PARTNO_MASK       = 0x0000fff0
    CPUID_PARTNO_POS        = 4
    CPUID_REVISION_MASK     = 0x0000000f
    CPUID_REVISION_POS      = 0

    NVIC_AIRCR = 0xE000ED0C
    NVIC_AIRCR_VECTKEY      = (0x5FA << 16)
    NVIC_AIRCR_VECTRESET    = (1 << 0)
    NVIC_AIRCR_SYSRESETREQ  = (1 << 2)

    # Core Register Selector Register
    DCRSR = 0xE000EDF4
    DCRSR_REGWnR = (1 << 16)
    DCRSR_REGSEL = 0x1F

    # Core Register Data Register
    DCRDR = 0xE000EDF8
    
    # Debug Halting Control and Status Register
    DHCSR = 0xE000EDF0
    C_DEBUGEN   = (1 << 0)
    C_HALT      = (1 << 1)
    C_STEP      = (1 << 2)
    C_MASKINTS  = (1 << 3)
    C_SNAPSTALL = (1 << 5)
    S_REGRDY    = (1 << 16)
    S_HALT      = (1 << 17)
    S_SLEEP     = (1 << 18)
    S_LOCKUP    = (1 << 19)
    S_RETIRE_ST = (1 << 24)
    S_RESET_ST  = (1 << 25)

    # Debug Exception and Monitor Control Register
    DEMCR = 0xE000EDFC
    DEMCR_TRCENA       = (1 << 24)
    DEMCR_VC_HARDERR   = (1 << 10)
    DEMCR_VC_BUSERR    = (1 << 8)
    DEMCR_VC_CORERESET = (1 << 0)

    DBGKEY = (0xA05F << 16)

    def __init__(self, link, dp, ap):
        self.link = link
        self.dp = dp
        self.ap = ap

        self.arch = 0
        self.core = 0

    ## @brief Read the CPUID register and determine core type.
    def readCoreType(self):
        cpuid = self.ap.read32(CortexM.CPUID)

        if (cpuid & CortexM.CPUID_IMPLEMENTER_MASK) >> CortexM.CPUID_IMPLEMENTER_POS != CortexM.CPUID_IMPLEMENTER_ARM:
            logging.warning("CPU implementer is not ARM!")

        self.arch = (cpuid & CortexM.CPUID_ARCHITECTURE_MASK) >> CortexM.CPUID_ARCHITECTURE_POS
        self.core = (cpuid & CortexM.CPUID_PARTNO_MASK)       >> CortexM.CPUID_PARTNO_POS
        logging.info("CPU core is %s", CORE_TYPE_NAME[self.core])

    def halt(self):
        self.ap.writeMemory(CortexM.DHCSR, CortexM.DBGKEY | CortexM.C_DEBUGEN | CortexM.C_HALT)
        self.dp.flush()

    def resume(self):
        if self.getState() != CortexM.TARGET_HALTED: return
        
        self.ap.writeMemory(CortexM.DHCSR, CortexM.DBGKEY | CortexM.C_DEBUGEN)
        self.dp.flush()

    def reset(self, software_reset=True):
        """reset a core. After a call to this function, the core is running"""
        if software_reset:
            try:
                self.ap.writeMemory(CortexM.NVIC_AIRCR, CortexM.NVIC_AIRCR_VECTKEY | CortexM.NVIC_AIRCR_SYSRESETREQ)
                self.dp.flush() # Without a flush a transfer error can occur
            except DAPAccess.TransferError:
                self.dp.flush()
        else:
            self.dp.reset()

        # Now wait for the system to come out of reset. Keep reading the DHCSR until
        # we get a good response with S_RESET_ST cleared, or we time out.
        startTime = time.time()
        while time.time() - startTime < 2.0:
            try:
                dhcsr = self.ap.read32(CortexM.DHCSR)
                if (dhcsr & CortexM.S_RESET_ST) == 0: break
            except DAPAccess.TransferError:
                self.dp.flush()
                time.sleep(0.01)

    def getState(self):
        dhcsr = self.ap.readMemory(CortexM.DHCSR)
        if dhcsr & CortexM.S_RESET_ST:
            newDhcsr = self.ap.readMemory(CortexM.DHCSR)
            if (newDhcsr & CortexM.S_RESET_ST) and not (newDhcsr & CortexM.S_RETIRE_ST):
                return CortexM.TARGET_RESET
        if dhcsr & CortexM.S_LOCKUP:
            return CortexM.TARGET_LOCKUP
        elif dhcsr & CortexM.S_SLEEP:
            return CortexM.TARGET_SLEEPING
        elif dhcsr & CortexM.S_HALT:
            return CortexM.TARGET_HALTED
        else:
            return CortexM.TARGET_RUNNING

    def isRunning(self):
        return self.getState() == CortexM.TARGET_RUNNING

    def isHalted(self):
        return self.getState() == CortexM.TARGET_HALTED

    def registerNameToIndex(self, reg):
        if isinstance(reg, str):
            try:
                reg = CORE_REGISTER[reg.lower()]
            except KeyError:
                logging.error('cannot find %s core register', reg)
                return
        return reg

    def readCoreRegister(self, reg):
        regIndex = self.registerNameToIndex(reg)
        regValue = self.readCoreRegisterRaw(regIndex)
        # Convert int to float.
        if regIndex >= 0x40:
            regValue = conversion.u32BEToFloat32BE(regValue)
        return regValue

    def readCoreRegisterRaw(self, reg):
        vals = self.readCoreRegistersRaw([reg])
        return vals[0]

    def readCoreRegistersRaw(self, reg_list):
        reg_list = [self.registerNameToIndex(reg) for reg in reg_list]

        # Sanity check register values
        for reg in reg_list:
            if reg not in CORE_REGISTER.values():
                raise ValueError("unknown reg: %d" % reg)
            elif ((reg >= 128) or (reg == 33)) and (not self.has_fpu):
                raise ValueError("attempt to read FPU register without FPU")

        # Begin all reads and writes
        dhcsr_cb_list = []
        reg_cb_list = []
        for reg in reg_list:
            if (reg < 0) and (reg >= -4):
                reg = CORE_REGISTER['cfbp']

            self.ap.writeMemory(CortexM.DCRSR, reg)

            # Technically, we need to poll S_REGRDY in DHCSR here before reading DCRDR. But
            # we're running so slow compared to the target that it's not necessary.
            # Read it and assert that S_REGRDY is set

            dhcsr_cb = self.ap.readMemory(CortexM.DHCSR, now=False)
            reg_cb = self.ap.readMemory(CortexM.DCRDR, now=False)
            dhcsr_cb_list.append(dhcsr_cb)
            reg_cb_list.append(reg_cb)

        # Read all results
        reg_vals = []
        for reg, reg_cb, dhcsr_cb in zip(reg_list, reg_cb_list, dhcsr_cb_list):
            dhcsr_val = dhcsr_cb()
            assert dhcsr_val & CortexM.S_REGRDY
            val = reg_cb()

            # Special handling for registers that are combined into a single DCRSR number.
            if (reg < 0) and (reg >= -4):
                val = (val >> ((-reg - 1) * 8)) & 0xff

            reg_vals.append(val)

        return reg_vals

    def writeCoreRegister(self, reg, data):
        regIndex = self.registerNameToIndex(reg)
        # Convert float to int.
        if regIndex >= 0x40:
            data = conversion.float32beToU32be(data)
        self.writeCoreRegisterRaw(regIndex, data)

    def writeCoreRegisterRaw(self, reg, data):
        self.writeCoreRegistersRaw([reg], [data])

    def writeCoreRegistersRaw(self, reg_list, data_list):
        """Write one or more core registers"""
        assert len(reg_list) == len(data_list)
        reg_list = [self.registerNameToIndex(reg) for reg in reg_list]

        # Sanity check register values
        for reg in reg_list:
            if reg not in CORE_REGISTER.values():
                raise ValueError("unknown reg: %d" % reg)
            elif ((reg >= 128) or (reg == 33)) and (not self.has_fpu):
                raise ValueError("attempt to write FPU register without FPU")

        # Read special register if it is present in the list
        for reg in reg_list:
            if (reg < 0) and (reg >= -4):
                specialRegValue = self.readCoreRegister(CORE_REGISTER['cfbp'])
                break

        # Write out registers
        dhcsr_cb_list = []
        for reg, data in zip(reg_list, data_list):
            if (reg < 0) and (reg >= -4):
                # Mask in the new special register value so we don't modify the other register
                # values that share the same DCRSR number.
                shift = (-reg - 1) * 8
                mask = 0xffffffff ^ (0xff << shift)
                data = (specialRegValue & mask) | ((data & 0xff) << shift)
                specialRegValue = data # update special register for other writes that might be in the list
                reg = CORE_REGISTER['cfbp']

            self.ap.writeMemory(CortexM.DCRDR, data)
            self.ap.writeMemory(CortexM.DCRSR, reg | CortexM.DCRSR_REGWnR)     #start write transfer

            # Technically, we need to poll S_REGRDY in DHCSR here to ensure the
            # register write has completed.
            # Read it and assert that S_REGRDY is set
            dhcsr_cb = self.ap.readMemory(CortexM.DHCSR, now=False)
            dhcsr_cb_list.append(dhcsr_cb)

        # Make sure S_REGRDY was set for all register writes
        for dhcsr_cb in dhcsr_cb_list:
            dhcsr_val = dhcsr_cb()
            assert dhcsr_val & CortexM.S_REGRDY
