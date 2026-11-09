"""High level RISC-V debug target: halt/resume, registers, CSRs and memory."""

import time

from pyocd.probe.pydapaccess.cmsis_dap_core import Pin

from . import csr
from .dm import (DM, AAMSIZE_8BITS, AAMSIZE_16BITS, AAMSIZE_32BITS,
                 DM_CONTROL_DMACTIVE, DM_CONTROL_HALTREQ,
                 DM_CONTROL_SETRESETHALTREQ, DM_STATUS_HASRESETHALTREQ)
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

# ABI names of x0-x31, used to build the register name table.
GPR_ABI_NAMES = (
    "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
    "s0", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
    "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
    "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6",
)


def register_names():
    """Return the ``{name: register number}`` table of the debug register space."""
    names = {}
    for index, alias in enumerate(GPR_ABI_NAMES):
        names["x%d" % index] = REG_X0 + index
        names[alias] = REG_X0 + index
    names["fp"] = REG_X0 + 8
    names["pc"] = REG_PC
    for index in range(32):
        names["f%d" % index] = REG_F0 + index
    for number, name in csr.CSR_NAMES.items():
        names[name] = REG_CSR_BASE + number
    names["priv"] = REG_PRIV
    return names


class RISCVError(Exception):
    """Raised for target level failures."""


class _LinkShim(object):
    """Mimics pyOCD's ``ap.dp.link`` so xlink.py can open/close the link."""

    def __init__(self, target):
        self._target = target

    def open(self):
        self._target.open()

    def close(self):
        self._target.close()


class _DpShim(object):
    def __init__(self, target):
        self.link = _LinkShim(target)


class _ApShim(object):
    def __init__(self, target):
        self.dp = _DpShim(target)


class RISCV(object):
    """RISC-V debug target built from DTM, DMI and DM layers."""

    def __init__(self, protocol=None, irlen=5, dtm=None):
        self.dtm = dtm if dtm is not None else DTM(protocol, irlen)
        self.dmi = DMI(self.dtm)
        self.dm = DM(self.dmi)
        self.idcode = 0
        self.dtmcs = 0
        self.opened = False
        self.mode = 'rv'
        self.core_regs = register_names()
        self.ap = _ApShim(self)

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

    def _read_bytes(self, addr, length):
        if length == 0:
            return b""
        width, aamsize = self._memory_access_width(addr, length)
        data = bytearray()
        for offset in range(0, length, width):
            value = self.dm.read_memory(addr + offset, aamsize)
            data += (value & ((1 << (width * 8)) - 1)).to_bytes(width, "little")
        return bytes(data)

    def _write_bytes(self, addr, data):
        data = bytes(data)
        if not data:
            return
        width, aamsize = self._memory_access_width(addr, len(data))
        for offset in range(0, len(data), width):
            value = int.from_bytes(data[offset:offset + width], "little")
            self.dm.write_memory(addr + offset, value, aamsize)

    def _read_transfer(self, addr, transfer_size):
        if transfer_size == 8:
            return self.dm.read_memory(addr, AAMSIZE_8BITS) & 0xFF
        if transfer_size == 16:
            return self.dm.read_memory(addr, AAMSIZE_16BITS) & 0xFFFF
        if transfer_size == 32:
            return self.dm.read_memory(addr, AAMSIZE_32BITS)
        raise RISCVError("unsupported transfer size %d" % transfer_size)

    def _write_transfer(self, addr, value, transfer_size):
        if transfer_size == 8:
            self.dm.write_memory(addr, value & 0xFF, AAMSIZE_8BITS)
        elif transfer_size == 16:
            self.dm.write_memory(addr, value & 0xFFFF, AAMSIZE_16BITS)
        elif transfer_size == 32:
            self.dm.write_memory(addr, value & 0xFFFFFFFF, AAMSIZE_32BITS)
        else:
            raise RISCVError("unsupported transfer size %d" % transfer_size)

    def read_memory(self, addr, transfer_size=32, now=True):
        """Read one memory location; ``now=False`` returns a callable."""
        if now:
            return self._read_transfer(addr, transfer_size)
        return lambda: self._read_transfer(addr, transfer_size)

    def write_memory(self, addr, value, transfer_size=32):
        """Write one memory location."""
        self._write_transfer(addr, value, transfer_size)

    def read8(self, addr, now=True):
        return self.read_memory(addr, 8, now)

    def read16(self, addr, now=True):
        return self.read_memory(addr, 16, now)

    def read32(self, addr, now=True):
        return self.read_memory(addr, 32, now)

    def write8(self, addr, value):
        self.write_memory(addr, value, 8)

    def write16(self, addr, value):
        self.write_memory(addr, value, 16)

    def write32(self, addr, value):
        self.write_memory(addr, value, 32)

    def read_memory_block8(self, addr, size):
        """Read a block of bytes; returns an array of byte values."""
        return list(self._read_bytes(addr, size))

    def write_memory_block8(self, addr, data):
        self._write_bytes(addr, data)

    def read_memory_block32(self, addr, size):
        """Read ``size`` aligned words; returns an array of word values."""
        return [self.dm.read_memory(addr + index * 4, AAMSIZE_32BITS)
                for index in range(size)]

    def write_memory_block32(self, addr, data):
        for index, value in enumerate(data):
            self.dm.write_memory(addr + index * 4, value & 0xFFFFFFFF, AAMSIZE_32BITS)

    # ------------------------------------------------------------------
    # Core registers
    # ------------------------------------------------------------------
    def register_number(self, name):
        """Return the register number of ``name`` (e.g. ``ra``, ``misa``)."""
        if isinstance(name, int):
            return name
        try:
            return self.core_regs[name.lower()]
        except KeyError:
            raise RISCVError("unknown register name '%s'" % name)

    def read_core_register_raw(self, reg):
        return self.read_register(self.register_number(reg))

    def read_core_registers_raw(self, reg_list):
        return [self.read_core_register_raw(reg) for reg in reg_list]

    def write_core_register_raw(self, reg, data):
        self.write_register(self.register_number(reg), data)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------
    @property
    def _link_protocol(self):
        """The CMSIS-DAP protocol behind the DTM, when the link provides one."""
        return getattr(self.dtm, "_protocol", None)

    def _set_reset(self, asserted):
        protocol = self._link_protocol
        if protocol is None or not hasattr(protocol, "set_swj_pins"):
            raise RISCVError("the link cannot drive nRESET")
        protocol.set_swj_pins(0 if asserted else Pin.nRESET, Pin.nRESET)

    def reset(self):
        """Pulse nRESET and let the hart run."""
        self._set_reset(True)
        try:
            time.sleep(0.05)
        finally:
            self._set_reset(False)
        self.dtm.reset_tap()
        self.dm.activate()      # the debug module may be reset with the hart

    def reset_and_halt(self):
        """Reset the target and halt the hart as reset is released."""
        self._set_reset(True)
        try:
            time.sleep(0.02)
            self.dtm.reset_tap()
            self.dm.activate()
            control = DM_CONTROL_DMACTIVE | DM_CONTROL_HALTREQ
            if self.dm.read_dmstatus() & DM_STATUS_HASRESETHALTREQ:
                control |= DM_CONTROL_SETRESETHALTREQ
            self.dm.write_dmcontrol(control)
        finally:
            self._set_reset(False)
        self.dm.wait_halted()
