"""RISC-V Debug Transport Module (DTM) driven by CMSIS-DAP JTAG sequences.

The DTM is the JTAG TAP of a RISC-V debug system. It exposes three 5-bit
instructions: IDCODE, DTMCS and DMI. CMSIS-DAP cannot use its ARM JTAG-DP
transfer command for this, so every transaction is built from raw
``DAP_JTAG_SEQUENCE`` commands.

A target may put the RISC-V TAP anywhere in a multi-device JTAG chain. The
``ir_pre``/``ir_post`` fields are the number of bypass bits before/after the
DTM instruction in the chain IR, and ``dr_pre``/``dr_post`` are the number of
bypass TAPs before/after it in the chain DR. This mirrors RV-Link's
``rvl_tap_config()``.
"""

from pyocd.probe.pydapaccess.cmsis_dap_core import Command, DAP_OK

# 5-bit JTAG instructions of the RISC-V DTM.
JTAG_IR_IDCODE = 0x01
JTAG_IR_DTMCS = 0x10
JTAG_IR_DMI = 0x11

DTMCS_DMI_RESET = 1 << 16
DTMCS_DMI_HARD_RESET = 1 << 17

DMI_OP_NOP = 0
DMI_OP_READ = 1
DMI_OP_WRITE = 2

DMI_STATUS_SUCCESS = 0
DMI_STATUS_FAILED = 2
DMI_STATUS_BUSY = 3


class DTMError(Exception):
    """Raised when a DTM/JTAG transaction fails."""


def discover_taps(protocol, bits=32):
    """Return the IR length of every TAP in the JTAG chain.

    This is the same scan used by RV-Link's probe.c: shift 32 one bits through
    the whole IR chain and count the ``01`` capture patterns.
    """
    dtm = DTM(protocol)
    dtm.configure_tap(0, 0, 0, 0)
    dtm.reset_tap()
    value = dtm.scan_ir(0xFFFFFFFF, bits=bits, capture=True)

    irs = []
    for _ in range(bits - 1):
        pair = value & 0x3
        if pair in (0x0, 0x2):
            if irs:
                irs[-1] += 1
        elif pair == 0x1:
            irs.append(1)
        value >>= 1
    return irs


class DTM(object):
    """Bit-bang the RISC-V DTM through CMSIS-DAP JTAG sequence commands."""

    def __init__(self, protocol, irlen=5, ir_pre=0, ir_post=0, dr_pre=0, dr_post=0):
        self._protocol = protocol
        self.irlen = irlen
        self.ir_pre = ir_pre
        self.ir_post = ir_post
        self.dr_pre = dr_pre
        self.dr_post = dr_post
        self.abits = 7
        self.idle = 1
        self._last_ir = None

    def configure_tap(self, ir_pre, ir_post, dr_pre, dr_post):
        """Select the position of the RISC-V TAP inside the JTAG chain."""
        self.ir_pre = ir_pre
        self.ir_post = ir_post
        self.dr_pre = dr_pre
        self.dr_post = dr_post
        self._last_ir = None

    # ------------------------------------------------------------------
    # JTAG primitives
    # ------------------------------------------------------------------
    def _jtag_sequence(self, sequences):
        """Execute ``(cycles, tms, capture, tdi)`` sequences.

        Each sequence drives a fixed TMS value for 1..64 TCK cycles. TDI data
        is always sent (LSB first, padded to bytes); TDO data is returned only
        for sequences with ``capture`` set, in command order.
        """
        cmd = [Command.DAP_JTAG_SEQUENCE, len(sequences)]
        for cycles, tms, capture, tdi in sequences:
            if not 1 <= cycles <= 64:
                raise ValueError("JTAG sequence length must be 1..64")
            info = (0 if cycles == 64 else cycles) & 0x3F
            info |= (tms & 1) << 6
            info |= (1 if capture else 0) << 7
            cmd.append(info)
            for i in range((cycles + 7) // 8):
                cmd.append((tdi >> (8 * i)) & 0xFF)

        self._protocol.interface.write(cmd)
        resp = self._protocol.interface.read()
        if resp[0] != Command.DAP_JTAG_SEQUENCE:
            raise DTMError("unexpected response 0x%02x to DAP_JTAG_SEQUENCE" % resp[0])
        if resp[1] != DAP_OK:
            raise DTMError("DAP_JTAG_SEQUENCE failed (status 0x%02x)" % resp[1])

        captured = []
        pos = 2
        for cycles, tms, capture, tdi in sequences:
            if capture:
                nbytes = (cycles + 7) // 8
                captured.append(int.from_bytes(bytes(resp[pos:pos + nbytes]), "little"))
                pos += nbytes
            else:
                captured.append(None)
        return captured

    def reset_tap(self):
        """Force the TAP to Test-Logic-Reset and back to Run-Test/Idle.

        The bit pattern is five TMS=1 cycles followed by three TMS=0 cycles.
        """
        self._protocol.swj_sequence([0x1F])
        self._last_ir = None

    def _ir_sequences(self, value, bits, capture):
        seqs = [(2, 1, False, 0), (2, 0, False, 0)]  # Idle -> Shift-IR
        if self.ir_pre:
            seqs.append((self.ir_pre, 0, False, 1))  # bypass before the TAP
        if self.ir_post:
            seqs.append((bits, 0, capture, value & ((1 << bits) - 1)))
            if self.ir_post > 1:
                seqs.append((self.ir_post - 1, 0, False, 1))
            seqs.append((1, 1, False, 1))  # last bypass bit & Exit1-IR
        else:
            if bits > 1:
                seqs.append((bits - 1, 0, capture, value & ((1 << (bits - 1)) - 1)))
                seqs.append((1, 1, capture, value >> (bits - 1)))
            else:
                seqs.append((1, 1, capture, value & 1))
        seqs += [(1, 1, False, 0), (1, 0, False, 0)]  # Update-IR -> Idle
        return seqs

    def scan_ir(self, value, bits=None, capture=False):
        """Shift an IR value through the configured TAP position."""
        bits = self.irlen if bits is None else bits
        seqs = self._ir_sequences(value, bits, capture)
        result = self._jtag_sequence(seqs)
        if not capture:
            return None
        captured = [item for item in result if item is not None]
        if self.ir_post or bits == 1:
            return captured[0] & ((1 << bits) - 1)
        return captured[0] | (captured[1] << (bits - 1))

    def _select_ir(self, ir):
        if self._last_ir == ir:
            return
        self.scan_ir(ir)
        self._last_ir = ir

    def scan_dr(self, value, bits):
        """Shift ``bits`` bits through the DTM's data register."""
        if not 1 <= bits <= 64:
            raise ValueError("DR scan length must be 1..64")
        value &= (1 << bits) - 1

        seqs = [(1, 1, False, 0), (2, 0, False, 0)]  # Idle -> Shift-DR
        if self.dr_pre:
            seqs.append((self.dr_pre, 0, False, 1))  # bypass TAPs before DTM
        if self.dr_post:
            seqs.append((bits, 0, True, value))
            if self.dr_post > 1:
                seqs.append((self.dr_post - 1, 0, False, 1))
            seqs.append((1, 1, False, 1))
        else:
            if bits > 1:
                seqs.append((bits - 1, 0, True, value & ((1 << (bits - 1)) - 1)))
                seqs.append((1, 1, True, value >> (bits - 1)))
            else:
                seqs.append((1, 1, True, value & 1))
        seqs += [(1, 1, False, 0), (1, 0, False, 0)]  # Update-DR -> Idle

        captured = [item for item in self._jtag_sequence(seqs) if item is not None]
        if self.dr_post or bits == 1:
            return captured[0] & ((1 << bits) - 1)
        return captured[0] | (captured[1] << (bits - 1))

    def run(self, cycles):
        """Keep the TAP in Run-Test/Idle for ``cycles`` TCK cycles."""
        while cycles > 0:
            n = min(cycles, 64)
            self._jtag_sequence([(n, 0, False, 0)])
            cycles -= n

    # ------------------------------------------------------------------
    # DTM registers
    # ------------------------------------------------------------------
    def read_idcode(self):
        """Read the 32-bit IDCODE register."""
        self._select_ir(JTAG_IR_IDCODE)
        return self.scan_dr(0, 32)

    def read_dtmcs(self):
        """Read and decode DTMCS, updating ``abits`` and ``idle``."""
        self._select_ir(JTAG_IR_DTMCS)
        value = self.scan_dr(0, 32)
        self.abits = (value >> 4) & 0x3F
        self.idle = (value >> 12) & 0x7
        return value

    def write_dtmcs(self, value):
        """Write DTMCS (used for DMI reset and hard reset)."""
        self._select_ir(JTAG_IR_DTMCS)
        self.scan_dr(value, 32)
        if self.idle > 1:
            self.run(self.idle - 1)

    def dmi_reset(self):
        """Clear the DMI sticky error flag."""
        self.write_dtmcs(DTMCS_DMI_RESET)

    def dmi_hard_reset(self):
        """Reset the DTM and DMI (debug spec 0.13 only)."""
        self.write_dtmcs(DTMCS_DMI_HARD_RESET)

    def dmi(self, addr, data, op):
        """Perform one DMI transaction.

        Returns ``(response_data, status)``. The response data belongs to the
        previous operation, so a read must be followed by a NOP transaction.
        """
        if addr < 0 or addr >= (1 << self.abits):
            raise ValueError("DMI address 0x%x does not fit in %d bits" % (addr, self.abits))

        self._select_ir(JTAG_IR_DMI)
        value = ((data & 0xFFFFFFFF) << 2) | (op & 0x3) | (addr << 34)
        result = self.scan_dr(value, 34 + self.abits)
        if self.idle > 1:
            self.run(self.idle - 1)
        return (result >> 2) & 0xFFFFFFFF, result & 0x3
