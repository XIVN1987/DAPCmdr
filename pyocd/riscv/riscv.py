"""High level RISC-V debug target: halt/resume, registers, CSRs and memory."""

import time

from . import csr
from .dm import DM, AAMSIZE_16BITS, AAMSIZE_32BITS
from .dmi import DMI
from .dtm import DTM

# GDB register numbering used by RV-Link.
REG_X0 = 0
REG_X31 = 31
REG_PC = 32
REG_F0 = 33
REG_F31 = 64
REG_CSR_BASE = 65
REG_PRIV = 4161


class RISCVError(Exception):
    """Raised for target level failures."""


class RISCV(object):
    """RISC-V debug target built from DTM, DMI and DM layers."""

    def __init__(self, protocol=None, irlen=5, dtm=None):
        self.dtm = dtm if dtm is not None else DTM(protocol, irlen)
        self.dmi = DMI(self.dtm)
        self.dm = DM(self.dmi)
        self.idcode = 0
        self.dtmcs = 0
        self.opened = False

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def open(self):
        """Reset the TAP, read IDCODE/DTMCS and activate the debug module."""
        self.dtm.reset_tap()

        for _ in range(3):
            self.idcode = self.dtm.read_idcode()
            if self.idcode not in (0x00000000, 0xFFFFFFFF):
                break
            self.dtm.reset_tap()
        else:
            raise RISCVError("invalid JTAG IDCODE 0x%08x" % self.idcode)

        self.dtmcs = self.dtm.read_dtmcs()
        if (self.dtmcs & 0xF) != 1:
            raise RISCVError("unsupported DTMCS version %d" % (self.dtmcs & 0xF))

        self.dm.activate()
        status = self.dm.read_dmstatus()
        if (status & 0xF) != 2:
            raise RISCVError("unsupported DMSTATUS version %d" % (status & 0xF))

        self.opened = True
        return self

    def close(self):
        """Disable the debug module."""
        if self.opened:
            self.dm.deactivate()
            self.opened = False

    @property
    def abits(self):
        return self.dtm.abits

    @property
    def idle(self):
        return self.dtm.idle

    # ------------------------------------------------------------------
    # Run control
    # ------------------------------------------------------------------
    def is_halted(self):
        return self.dm.is_halted()

    def wait_halted(self, timeout=1.0):
        self.dm.wait_halted(timeout)

    def halt(self):
        """Request the hart to enter debug mode and wait for it."""
        self.dm.halt()
        self.dm.wait_halted()

    def resume(self):
        """Clear single-step and let the hart run."""
        if self.dm.is_halted():
            dcsr = csr.Dcsr(self.dm.read_register(csr.CSR_DCSR))
            if dcsr.step:
                dcsr.step = 0
                self.dm.write_register(csr.CSR_DCSR, int(dcsr))
        self.dm.resume()

    def step(self):
        """Single-step and wait until the hart halts again."""
        self.dm.wait_halted()
        dcsr = csr.Dcsr(self.dm.read_register(csr.CSR_DCSR))
        dcsr.step = 1
        self.dm.write_register(csr.CSR_DCSR, int(dcsr))
        self.dm.resume()
        time.sleep(0.001)
        self.dm.wait_halted()

    def enable_ebreak(self):
        """Let ebreak instructions enter debug mode in all privilege modes."""
        dcsr = csr.Dcsr(self.dm.read_register(csr.CSR_DCSR))
        dcsr.ebreakm = 1
        dcsr.ebreaks = 1
        dcsr.ebreaku = 1
        self.dm.write_register(csr.CSR_DCSR, int(dcsr))

    def read_dcsr(self):
        return csr.Dcsr(self.dm.read_register(csr.CSR_DCSR))

    # ------------------------------------------------------------------
    # Core registers
    # ------------------------------------------------------------------
    def read_gpr(self, index):
        if index == 0:
            return 0
        return self.dm.read_register(csr.gpr_regno(index))

    def write_gpr(self, index, value):
        if index == 0:
            return
        self.dm.write_register(csr.gpr_regno(index), value)

    def read_fpr(self, index):
        return self.dm.read_register(csr.fpr_regno(index))

    def write_fpr(self, index, value):
        self.dm.write_register(csr.fpr_regno(index), value)

    def read_pc(self):
        return self.dm.read_register(csr.CSR_DPC)

    def write_pc(self, value):
        self.dm.write_register(csr.CSR_DPC, value)

    def read_csr(self, number):
        return self.dm.read_register(number)

    def write_csr(self, number, value):
        self.dm.write_register(number, value)

    def read_priv(self):
        """Current privilege mode, encoded in dcsr.prv."""
        return self.read_dcsr().prv

    def write_priv(self, priv):
        dcsr = self.read_dcsr()
        dcsr.prv = priv
        self.dm.write_register(csr.CSR_DCSR, int(dcsr))

    def read_register(self, regno):
        """Read a register using the RV-Link/GDB numbering."""
        if REG_X0 <= regno <= REG_X31:
            return self.read_gpr(regno)
        if regno == REG_PC:
            return self.read_pc()
        if REG_F0 <= regno <= REG_F31:
            return self.read_fpr(regno - REG_F0)
        if REG_CSR_BASE <= regno <= REG_CSR_BASE + 0xFFF:
            return self.read_csr(regno - REG_CSR_BASE)
        if regno == REG_PRIV:
            return self.read_priv()
        raise RISCVError("unknown register number %d" % regno)

    def write_register(self, regno, value):
        """Write a register using the RV-Link/GDB numbering."""
        if REG_X0 <= regno <= REG_X31:
            self.write_gpr(regno, value)
        elif regno == REG_PC:
            self.write_pc(value)
        elif REG_F0 <= regno <= REG_F31:
            self.write_fpr(regno - REG_F0, value)
        elif REG_CSR_BASE <= regno <= REG_CSR_BASE + 0xFFF:
            self.write_csr(regno - REG_CSR_BASE, value)
        elif regno == REG_PRIV:
            self.write_priv(value)
        else:
            raise RISCVError("unknown register number %d" % regno)

    def read_registers(self):
        """Read x0-x31 and pc into a 33 element list."""
        regs = [0] * 33
        for index in range(1, 32):
            regs[index] = self.read_gpr(index)
        regs[REG_PC] = self.read_pc()
        return regs

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------
    @staticmethod
    def _memory_access_width(addr, length):
        if (addr & 3) == 0 and (length & 3) == 0:
            return 4, AAMSIZE_32BITS
        if (addr & 1) == 0 and (length & 1) == 0:
            return 2, AAMSIZE_16BITS
        return 1, AAMSIZE_8BITS

    def read_memory(self, addr, length):
        """Read ``length`` bytes from target memory."""
        if length == 0:
            return b""
        width, aamsize = self._memory_access_width(addr, length)
        data = bytearray()
        for offset in range(0, length, width):
            value = self.dm.read_memory(addr + offset, aamsize)
            data += (value & ((1 << (width * 8)) - 1)).to_bytes(width, "little")
        return bytes(data)

    def write_memory(self, addr, data):
        """Write bytes to target memory."""
        data = bytes(data)
        if not data:
            return
        width, aamsize = self._memory_access_width(addr, len(data))
        for offset in range(0, len(data), width):
            chunk = data[offset:offset + width]
            value = int.from_bytes(chunk, "little")
            self.dm.write_memory(addr + offset, value, aamsize)

    def read_u32(self, addr):
        return self.dm.read_memory(addr, AAMSIZE_32BITS)

    def write_u32(self, addr, value):
        self.dm.write_memory(addr, value, AAMSIZE_32BITS)
