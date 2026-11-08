"""CSR numbers, abstract register numbers and bit-field helpers for RISC-V debug."""

# Machine-mode CSRs
CSR_MSTATUS = 0x300
CSR_MISA = 0x301
CSR_MIE = 0x304
CSR_MTVEC = 0x305
CSR_MCOUNTINHIBIT = 0x320
CSR_MSCRATCH = 0x340
CSR_MEPC = 0x341
CSR_MCAUSE = 0x342
CSR_MTVAL = 0x343
CSR_MIP = 0x344

# Trigger CSRs
CSR_TSELECT = 0x7A0
CSR_TDATA1 = 0x7A1
CSR_TDATA2 = 0x7A2
CSR_TDATA3 = 0x7A3
CSR_TINFO = 0x7A4
CSR_MCONTROL = 0x7A5

# Debug CSRs
CSR_DCSR = 0x7B0
CSR_DPC = 0x7B1
CSR_DSCRATCH0 = 0x7B2
CSR_DSCRATCH1 = 0x7B3

# Read-only machine information CSRs
CSR_MVENDORID = 0xF11
CSR_MARCHID = 0xF12
CSR_MIMPID = 0xF13
CSR_MHARTID = 0xF14

CSR_NAMES = {
    CSR_MSTATUS: "mstatus",
    CSR_MISA: "misa",
    CSR_MIE: "mie",
    CSR_MTVEC: "mtvec",
    CSR_MCOUNTINHIBIT: "mcountinhibit",
    CSR_MSCRATCH: "mscratch",
    CSR_MEPC: "mepc",
    CSR_MCAUSE: "mcause",
    CSR_MTVAL: "mtval",
    CSR_MIP: "mip",
    CSR_TSELECT: "tselect",
    CSR_TDATA1: "tdata1",
    CSR_TDATA2: "tdata2",
    CSR_TDATA3: "tdata3",
    CSR_TINFO: "tinfo",
    CSR_MCONTROL: "mcontrol",
    CSR_DCSR: "dcsr",
    CSR_DPC: "dpc",
    CSR_DSCRATCH0: "dscratch0",
    CSR_DSCRATCH1: "dscratch1",
    CSR_MVENDORID: "mvendorid",
    CSR_MARCHID: "marchid",
    CSR_MIMPID: "mimpid",
    CSR_MHARTID: "mhartid",
}


def csr_name(number):
    """Return the standard name for a CSR number, or a hex fallback."""
    return CSR_NAMES.get(number, "csr_0x%03x" % number)


# Abstract register numbers used by the Access Register command.
REGNO_GPR_BASE = 0x1000
REGNO_FPR_BASE = 0x1020


def gpr_regno(index):
    """Abstract register number of integer register x<index>."""
    return REGNO_GPR_BASE + index


def fpr_regno(index):
    """Abstract register number of floating point register f<index>."""
    return REGNO_FPR_BASE + index


# dcsr.cause values (RISC-V debug spec 0.13).
DCSR_CAUSE_EBREAK = 1
DCSR_CAUSE_TRIGGER = 2
DCSR_CAUSE_HALTREQ = 3
DCSR_CAUSE_STEP = 4
DCSR_CAUSE_RESETHALTREQ = 5

DCSR_CAUSE_NAMES = {
    DCSR_CAUSE_EBREAK: "ebreak",
    DCSR_CAUSE_TRIGGER: "trigger",
    DCSR_CAUSE_HALTREQ: "haltreq",
    DCSR_CAUSE_STEP: "step",
    DCSR_CAUSE_RESETHALTREQ: "resethaltreq",
}


class Dcsr(object):
    """Bit-field view of the RISC-V ``dcsr`` register."""

    def __init__(self, value=0):
        self.value = value & 0xFFFFFFFF

    prv = property(lambda self: (self.value >> 0) & 0x3,
                   lambda self, v: setattr(self, "value", (self.value & ~0x3) | (v & 0x3)))
    step = property(lambda self: (self.value >> 2) & 0x1,
                    lambda self, v: setattr(self, "value", (self.value & ~(1 << 2)) | ((v & 1) << 2)))
    nmip = property(lambda self: (self.value >> 3) & 0x1,
                    lambda self, v: setattr(self, "value", (self.value & ~(1 << 3)) | ((v & 1) << 3)))
    mprven = property(lambda self: (self.value >> 4) & 0x1,
                      lambda self, v: setattr(self, "value", (self.value & ~(1 << 4)) | ((v & 1) << 4)))
    cause = property(lambda self: (self.value >> 6) & 0x7,
                     lambda self, v: setattr(self, "value", (self.value & ~(0x7 << 6)) | ((v & 0x7) << 6)))
    stoptime = property(lambda self: (self.value >> 9) & 0x1,
                        lambda self, v: setattr(self, "value", (self.value & ~(1 << 9)) | ((v & 1) << 9)))
    stopcount = property(lambda self: (self.value >> 10) & 0x1,
                         lambda self, v: setattr(self, "value", (self.value & ~(1 << 10)) | ((v & 1) << 10)))
    stepie = property(lambda self: (self.value >> 11) & 0x1,
                      lambda self, v: setattr(self, "value", (self.value & ~(1 << 11)) | ((v & 1) << 11)))
    ebreaku = property(lambda self: (self.value >> 12) & 0x1,
                       lambda self, v: setattr(self, "value", (self.value & ~(1 << 12)) | ((v & 1) << 12)))
    ebreaks = property(lambda self: (self.value >> 13) & 0x1,
                       lambda self, v: setattr(self, "value", (self.value & ~(1 << 13)) | ((v & 1) << 13)))
    ebreakm = property(lambda self: (self.value >> 15) & 0x1,
                       lambda self, v: setattr(self, "value", (self.value & ~(1 << 15)) | ((v & 1) << 15)))
    xdebugver = property(lambda self: (self.value >> 28) & 0xF,
                         lambda self, v: setattr(self, "value", (self.value & ~(0xF << 28)) | ((v & 0xF) << 28)))

    def __int__(self):
        return self.value

    def __repr__(self):
        return "Dcsr(0x%08x)" % self.value


class Mcontrol(object):
    """Bit-field view of a type=2 match trigger's ``tdata1`` (mcontrol)."""

    def __init__(self, value=0):
        self.value = value & 0xFFFFFFFF

    load = property(lambda self: (self.value >> 0) & 0x1,
                    lambda self, v: setattr(self, "value", (self.value & ~(1 << 0)) | ((v & 1) << 0)))
    store = property(lambda self: (self.value >> 1) & 0x1,
                     lambda self, v: setattr(self, "value", (self.value & ~(1 << 1)) | ((v & 1) << 1)))
    execute = property(lambda self: (self.value >> 2) & 0x1,
                       lambda self, v: setattr(self, "value", (self.value & ~(1 << 2)) | ((v & 1) << 2)))
    u = property(lambda self: (self.value >> 3) & 0x1,
                 lambda self, v: setattr(self, "value", (self.value & ~(1 << 3)) | ((v & 1) << 3)))
    s = property(lambda self: (self.value >> 4) & 0x1,
                 lambda self, v: setattr(self, "value", (self.value & ~(1 << 4)) | ((v & 1) << 4)))
    m = property(lambda self: (self.value >> 6) & 0x1,
                 lambda self, v: setattr(self, "value", (self.value & ~(1 << 6)) | ((v & 1) << 6)))
    match = property(lambda self: (self.value >> 7) & 0xF,
                     lambda self, v: setattr(self, "value", (self.value & ~(0xF << 7)) | ((v & 0xF) << 7)))
    chain = property(lambda self: (self.value >> 11) & 0x1,
                     lambda self, v: setattr(self, "value", (self.value & ~(1 << 11)) | ((v & 1) << 11)))
    action = property(lambda self: (self.value >> 12) & 0xF,
                      lambda self, v: setattr(self, "value", (self.value & ~(0xF << 12)) | ((v & 0xF) << 12)))
    sizelo = property(lambda self: (self.value >> 16) & 0x3,
                      lambda self, v: setattr(self, "value", (self.value & ~(0x3 << 16)) | ((v & 0x3) << 16)))
    timing = property(lambda self: (self.value >> 18) & 0x1,
                      lambda self, v: setattr(self, "value", (self.value & ~(1 << 18)) | ((v & 1) << 18)))
    select = property(lambda self: (self.value >> 19) & 0x1,
                      lambda self, v: setattr(self, "value", (self.value & ~(1 << 19)) | ((v & 1) << 19)))
    hit = property(lambda self: (self.value >> 20) & 0x1,
                   lambda self, v: setattr(self, "value", (self.value & ~(1 << 20)) | ((v & 1) << 20)))
    maskmax = property(lambda self: (self.value >> 21) & 0x3F,
                       lambda self, v: setattr(self, "value", (self.value & ~(0x3F << 21)) | ((v & 0x3F) << 21)))
    dmode = property(lambda self: (self.value >> 27) & 0x1,
                     lambda self, v: setattr(self, "value", (self.value & ~(1 << 27)) | ((v & 1) << 27)))
    type = property(lambda self: (self.value >> 28) & 0xF,
                    lambda self, v: setattr(self, "value", (self.value & ~(0xF << 28)) | ((v & 0xF) << 28)))

    def __int__(self):
        return self.value

    def __repr__(self):
        return "Mcontrol(0x%08x)" % self.value
