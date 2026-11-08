"""RISC-V Debug Module (DM) registers and abstract commands (debug spec 0.13)."""

import time

# Debug module register addresses (DMI address space).
DM_DATA0 = 0x04
DM_DATA1 = 0x05
DM_DATA2 = 0x06
DM_DATA3 = 0x07
DM_DATA4 = 0x08
DM_DATA5 = 0x09
DM_DATA6 = 0x0A
DM_DATA7 = 0x0B
DM_DATA8 = 0x0C
DM_DATA9 = 0x0D
DM_DATA10 = 0x0E
DM_DATA11 = 0x0F

DM_CONTROL = 0x10
DM_STATUS = 0x11
DM_HART_INFO = 0x12
DM_HALT_SUM1 = 0x13
DM_HAWINDOWSEL = 0x14
DM_HAWINDOW = 0x15
DM_ABSTRACT_CS = 0x16
DM_ABSTRACT_CMD = 0x17
DM_ABSTRACT_AUTO = 0x18
DM_CONFSTRPTR0 = 0x19
DM_CONFSTRPTR1 = 0x1A
DM_CONFSTRPTR2 = 0x1B
DM_CONFSTRPTR3 = 0x1C
DM_NEXT = 0x1D

DM_PROG_BUF0 = 0x20
DM_PROG_BUF15 = 0x2F

DM_AUTH_DATA = 0x30
DM_HALT_SUM2 = 0x34
DM_HALT_SUM3 = 0x35
DM_SB_ADDR3 = 0x37
DM_SB_CS = 0x38
DM_SB_ADDR0 = 0x39
DM_SB_ADDR1 = 0x3A
DM_SB_ADDR2 = 0x3B
DM_SB_DATA0 = 0x3C
DM_SB_DATA1 = 0x3D
DM_SB_DATA2 = 0x3E
DM_SB_DATA3 = 0x3F
DM_HALT_SUM0 = 0x40

# dmcontrol bits
DM_CONTROL_DMACTIVE = 1 << 0
DM_CONTROL_NDMRESET = 1 << 1
DM_CONTROL_CLRRESETHALTREQ = 1 << 2
DM_CONTROL_SETRESETHALTREQ = 1 << 3
DM_CONTROL_HARTSELHI_SHIFT = 6
DM_CONTROL_HARTSELHI_MASK = 0x3FF
DM_CONTROL_HARTSELO_SHIFT = 16
DM_CONTROL_HARTSELO_MASK = 0x3FF
DM_CONTROL_HASEL = 1 << 26
DM_CONTROL_ACKHAVERESET = 1 << 28
DM_CONTROL_HARTRESET = 1 << 29
DM_CONTROL_RESUMEREQ = 1 << 30
DM_CONTROL_HALTREQ = 1 << 31

# dmstatus bits
DM_STATUS_VERSION_MASK = 0xF
DM_STATUS_CONFSTRPTRVALID = 1 << 4
DM_STATUS_HASRESETHALTREQ = 1 << 5
DM_STATUS_AUTHBUSY = 1 << 6
DM_STATUS_AUTHENTICATED = 1 << 7
DM_STATUS_ANYHALTED = 1 << 8
DM_STATUS_ALLHALTED = 1 << 9
DM_STATUS_ANYRUNNING = 1 << 10
DM_STATUS_ALLRUNNING = 1 << 11
DM_STATUS_ANYUNAVAIL = 1 << 12
DM_STATUS_ALLUNAVAIL = 1 << 13
DM_STATUS_ANYNONEXISTENT = 1 << 14
DM_STATUS_ALLNONEXISTENT = 1 << 15
DM_STATUS_ANYRESUMEACK = 1 << 16
DM_STATUS_ALLRESUMEACK = 1 << 17
DM_STATUS_ANYHAVERESET = 1 << 18
DM_STATUS_ALLHAVERESET = 1 << 19
DM_STATUS_IMPEBREAK = 1 << 22

# abstractcs bits
ABSTRACT_CS_DATACOUNT_MASK = 0xF
ABSTRACT_CS_CMDEERR_SHIFT = 8
ABSTRACT_CS_CMDEERR_MASK = 0x7
ABSTRACT_CS_BUSY = 1 << 12
ABSTRACT_CS_PROGBUFSIZE_SHIFT = 24
ABSTRACT_CS_PROGBUFSIZE_MASK = 0x1F

# hartinfo bits
HART_INFO_DATAADDR_MASK = 0xFFF
HART_INFO_DATASIZE_SHIFT = 12
HART_INFO_DATAACCESS = 1 << 16
HART_INFO_NSCRATCH_SHIFT = 20
HART_INFO_NSCRATCH_MASK = 0xF

# Abstract command types (command[31:24]).
CMD_ACCESS_REG = 0
CMD_QUICK_ACCESS = 1
CMD_ACCESS_MEM = 2

# Access Register command fields.
CMD_REG_REGNO_MASK = 0xFFFF
CMD_REG_WRITE = 1 << 16
CMD_REG_TRANSFER = 1 << 17
CMD_REG_POSTEXEC = 1 << 18
CMD_REG_POSTINCREMENT = 1 << 19
CMD_REG_AARSIZE_SHIFT = 20
CMD_REG_AARSIZE_MASK = 0x7

# Access Memory command fields.
CMD_MEM_TARGET_SPECIFIC_SHIFT = 14
CMD_MEM_WRITE = 1 << 17
CMD_MEM_POSTINCREMENT = 1 << 19
CMD_MEM_AAMSIZE_SHIFT = 20
CMD_MEM_AAMSIZE_MASK = 0x7
CMD_MEM_AAMVIRTUAL = 1 << 23

AAMSIZE_8BITS = 0
AAMSIZE_16BITS = 1
AAMSIZE_32BITS = 2
AAMSIZE_64BITS = 3
AAMSIZE_128BITS = 4

AARSIZE_32BITS = 2
AARSIZE_64BITS = 3

CMDERR_MESSAGES = {
    0: "none",
    1: "busy",
    2: "not supported",
    3: "exception",
    4: "halt/resume",
    5: "bus",
    6: "reserved",
    7: "other",
}


class DMError(Exception):
    """Raised for debug module level failures."""


class AbstractCommandError(DMError):
    """Raised when the debug module reports abstractcs.cmderr != 0."""

    def __init__(self, cmderr):
        self.cmderr = cmderr
        super(AbstractCommandError, self).__init__(
            "abstract command error %d (%s)" % (cmderr, CMDERR_MESSAGES.get(cmderr, "unknown")))


class DM(object):
    """Debug module control, abstract register/memory access and hart control."""

    def __init__(self, dmi, aarsize=AARSIZE_32BITS):
        self.dmi = dmi
        self.aarsize = aarsize

    # ------------------------------------------------------------------
    # Raw register access
    # ------------------------------------------------------------------
    def read(self, addr):
        return self.dmi.read(addr)

    def write(self, addr, value):
        self.dmi.write(addr, value)

    def read_dmcontrol(self):
        return self.read(DM_CONTROL)

    def write_dmcontrol(self, value):
        self.write(DM_CONTROL, value)

    def read_dmstatus(self):
        return self.read(DM_STATUS)

    def read_hartinfo(self):
        return self.read(DM_HART_INFO)

    def read_abstractcs(self):
        return self.read(DM_ABSTRACT_CS)

    def hartinfo_fields(self):
        hartinfo = self.read_hartinfo()
        return {
            "dataaddr": hartinfo & HART_INFO_DATAADDR_MASK,
            "datasize": (hartinfo >> HART_INFO_DATASIZE_SHIFT) & 0xF,
            "dataaccess": 1 if (hartinfo & HART_INFO_DATAACCESS) else 0,
            "nscratch": (hartinfo >> HART_INFO_NSCRATCH_SHIFT) & HART_INFO_NSCRATCH_MASK,
        }

    # ------------------------------------------------------------------
    # Debug module / hart control
    # ------------------------------------------------------------------
    def activate(self):
        """Pulse dmactive low, then enable the debug module."""
        self.write_dmcontrol(0)
        for _ in range(10):
            if not (self.read_dmcontrol() & DM_CONTROL_DMACTIVE):
                break
            time.sleep(0.01)
        else:
            raise DMError("debug module did not deactivate")

        self.write_dmcontrol(DM_CONTROL_DMACTIVE)
        for _ in range(10):
            if self.read_dmcontrol() & DM_CONTROL_DMACTIVE:
                return
            time.sleep(0.01)
        raise DMError("debug module did not activate")

    def deactivate(self):
        self.write_dmcontrol(0)

    def is_halted(self):
        return bool(self.read_dmstatus() & DM_STATUS_ALLHALTED)

    def halt(self):
        self.write_dmcontrol(DM_CONTROL_DMACTIVE | DM_CONTROL_HALTREQ)

    def resume(self):
        self.write_dmcontrol(DM_CONTROL_DMACTIVE | DM_CONTROL_RESUMEREQ)

    def wait_halted(self, timeout=1.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.read_dmstatus()
            if status & DM_STATUS_ALLHALTED:
                return
            time.sleep(0.001)
        raise DMError("hart did not enter debug mode")

    def wait_running(self, timeout=1.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.read_dmstatus()
            if status & DM_STATUS_ALLRUNNING:
                return
            time.sleep(0.001)
        raise DMError("hart did not resume")

    # ------------------------------------------------------------------
    # Abstract commands
    # ------------------------------------------------------------------
    def clear_abstract_errors(self):
        self.write(DM_ABSTRACT_CS, ABSTRACT_CS_CMDEERR_MASK << ABSTRACT_CS_CMDEERR_SHIFT)

    def _wait_abstract(self, timeout=1.0):
        deadline = time.time() + timeout
        while True:
            abstractcs = self.read_abstractcs()
            if not (abstractcs & ABSTRACT_CS_BUSY):
                break
            if time.time() > deadline:
                raise DMError("abstract command stayed busy")
            time.sleep(0.001)

        cmderr = (abstractcs >> ABSTRACT_CS_CMDEERR_SHIFT) & ABSTRACT_CS_CMDEERR_MASK
        if cmderr:
            self.clear_abstract_errors()
            raise AbstractCommandError(cmderr)
        return abstractcs

    def _access_register_control(self, regno, write=False, postexec=False, postincrement=False):
        return ((regno & CMD_REG_REGNO_MASK)
                | (CMD_REG_WRITE if write else 0)
                | CMD_REG_TRANSFER
                | (CMD_REG_POSTEXEC if postexec else 0)
                | (CMD_REG_POSTINCREMENT if postincrement else 0)
                | ((self.aarsize & CMD_REG_AARSIZE_MASK) << CMD_REG_AARSIZE_SHIFT))

    def _access_memory_control(self, aamsize, write=False, postincrement=False):
        return ((CMD_ACCESS_MEM << 24)
                | ((aamsize & CMD_MEM_AAMSIZE_MASK) << CMD_MEM_AAMSIZE_SHIFT)
                | (CMD_MEM_POSTINCREMENT if postincrement else 0)
                | (CMD_MEM_WRITE if write else 0))

    def read_register(self, regno):
        """Read a core register through the Access Register command."""
        command = (CMD_ACCESS_REG << 24) | self._access_register_control(regno, write=False)
        self.write(DM_ABSTRACT_CMD, command)
        self._wait_abstract()
        return self.read(DM_DATA0)

    def write_register(self, regno, value):
        """Write a core register through the Access Register command."""
        self.write(DM_DATA0, value & 0xFFFFFFFF)
        command = (CMD_ACCESS_REG << 24) | self._access_register_control(regno, write=True)
        self.write(DM_ABSTRACT_CMD, command)
        self._wait_abstract()

    def quick_access(self):
        """Execute the program buffer once and return data0."""
        self.write(DM_ABSTRACT_CMD, CMD_QUICK_ACCESS << 24)
        self._wait_abstract()
        return self.read(DM_DATA0)

    def read_memory(self, addr, aamsize=AAMSIZE_32BITS):
        """Read one memory element through the Access Memory command."""
        self.write(DM_DATA1, addr & 0xFFFFFFFF)
        self.write(DM_ABSTRACT_CMD, self._access_memory_control(aamsize, write=False))
        self._wait_abstract()
        return self.read(DM_DATA0)

    def write_memory(self, addr, value, aamsize=AAMSIZE_32BITS):
        """Write one memory element through the Access Memory command."""
        self.write(DM_DATA1, addr & 0xFFFFFFFF)
        self.write(DM_DATA0, value & 0xFFFFFFFF)
        self.write(DM_ABSTRACT_CMD, self._access_memory_control(aamsize, write=True))
        self._wait_abstract()
