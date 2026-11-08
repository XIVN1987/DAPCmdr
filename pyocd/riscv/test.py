"""RISC-V debug demo and self test.

The test sequence follows RV-Link's riscv-prober (probe.c): identify the DTM,
activate the debug module, halt the hart, dump DM information, access
registers/CSRs/memory, run the program buffer through quick access and probe
the trigger CSRs. Memory writes are only exercised when MEM_TEST_ADDR points
at a scratch RAM location.
"""

import os
import sys
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

os.environ["PATH"] = os.path.join(_REPO_ROOT, "libusb-1.0.24", "MinGW64", "dll") \
    + os.pathsep + os.environ["PATH"]

from pyocd.probe.pydapaccess.dap_access_api import DAPAccessIntf
from pyocd.probe.pydapaccess.cmsis_dap_core import CMSISDAPProtocol, DAP_JTAG_PORT
from pyocd.probe.pydapaccess.dap_access_cmsis_dap import _get_interfaces
from pyocd.riscv import csr
from pyocd.riscv.dm import (AbstractCommandError, DM_ABSTRACT_AUTO, DM_ABSTRACT_CMD,
                            DM_DATA0, DM_PROG_BUF0, DM_SB_CS)
from pyocd.riscv.dtm import DTM, discover_taps
from pyocd.riscv.riscv import RISCV

# Address used by probe.c to read memory; safe to read on GD32VF103/FE310.
PROBE_MEM_ADDR = 0x08000000
# Set this to a safe scratch RAM address to test memory writes, e.g. 0x20000000
# on GD32VF103 (SRAM).  It is disabled by default because writing RAM can
# corrupt the program being debugged.
MEM_TEST_ADDR = None


def csrr(rd, csr_number):
    """csrrs rd, csr, x0"""
    return (csr_number << 20) | (rd << 7) | 0x2073


def csrw(csr_number, src):
    """csrrw x0, csr, rs"""
    return (csr_number << 20) | (src << 15) | 0x1073


def sw(src, base, offset):
    """sw src, offset(base)"""
    offset &= 0xFFF
    return (((offset >> 5) & 0x7F) << 25) | (src << 20) | (base << 15) \
        | ((offset & 0x1F) << 7) | 0x2023


def print_dtm(target):
    value = target.idcode
    print("\nidcode: 0x%08x" % value)
    print("idcode.version: %d" % ((value >> 28) & 0xF))
    print("idcode.part_number: 0x%x" % ((value >> 12) & 0xFFFF))
    print("idcode.manuf_id: 0x%x" % ((value >> 1) & 0x7FF))

    value = target.dtmcs
    print("\ndtmcs: 0x%08x" % value)
    print("dtmcs.version: %d" % (value & 0xF))
    print("dtmcs.abits: %d" % ((value >> 4) & 0x3F))
    print("dtmcs.idle: %d" % ((value >> 12) & 0x7))


def print_dmstatus(dm):
    status = dm.read_dmstatus()
    print("dmstatus: 0x%08x" % status)
    print("dmstatus.version: %d" % (status & 0xF))
    print("dmstatus.confstrptrvalid: %d" % (1 if status & (1 << 4) else 0))
    print("dmstatus.hasresethaltreq: %d" % (1 if status & (1 << 5) else 0))
    print("dmstatus.authenticated: %d" % (1 if status & (1 << 7) else 0))
    print("dmstatus.anyhalted: %d" % (1 if status & (1 << 8) else 0))
    print("dmstatus.allhalted: %d" % (1 if status & (1 << 9) else 0))
    print("dmstatus.anyrunning: %d" % (1 if status & (1 << 10) else 0))
    print("dmstatus.allrunning: %d" % (1 if status & (1 << 11) else 0))
    print("dmstatus.impebreak: %d" % (1 if status & (1 << 22) else 0))


def test_debug_module(target):
    dm = target.dm

    print("\ndmstatus (before halt)")
    print_dmstatus(dm)

    print("\ndmcontrol: 0x%08x" % dm.read_dmcontrol())
    print("dmcontrol.dmactive: %d" % (dm.read_dmcontrol() & 1))

    print("\nhalt hart...")
    target.halt()
    print_dmstatus(dm)

    print("\nhartinfo: 0x%08x" % dm.read_hartinfo())
    hartinfo = dm.hartinfo_fields()
    print("hartinfo.dataaddr: %d" % hartinfo["dataaddr"])
    print("hartinfo.datasize: %d" % hartinfo["datasize"])
    print("hartinfo.dataaccess: %d (%s)" % (hartinfo["dataaccess"],
                                            "memory map" if hartinfo["dataaccess"] else "csr map"))
    print("hartinfo.nscratch: %d" % hartinfo["nscratch"])

    abstractcs = dm.read_abstractcs()
    print("\nabstractcs: 0x%08x" % abstractcs)
    print("abstractcs.datacount: %d" % (abstractcs & 0xF))
    print("abstractcs.progbufsize: %d" % ((abstractcs >> 24) & 0x1F))

    print("\nabstractauto test")
    dm.write(DM_ABSTRACT_AUTO, 0xFFFFFFFF)
    abstractauto = dm.read(DM_ABSTRACT_AUTO)
    print("abstractauto: 0x%08x" % abstractauto)
    print("abstractauto.autoexecdata: 0x%03x" % (abstractauto & 0xFFF))
    print("abstractauto.autoexecprogbuf: 0x%04x" % ((abstractauto >> 16) & 0xFFFF))
    dm.write(DM_ABSTRACT_AUTO, 0)

    sbcs = dm.read(DM_SB_CS)
    print("\nsbcs: 0x%08x" % sbcs)
    print("sbcs.sbaccess8: %d" % (sbcs & 1))
    print("sbcs.sbaccess16: %d" % ((sbcs >> 1) & 1))
    print("sbcs.sbaccess32: %d" % ((sbcs >> 2) & 1))
    print("sbcs.sbaccess64: %d" % ((sbcs >> 3) & 1))
    print("sbcs.sbaccess128: %d" % ((sbcs >> 4) & 1))
    print("sbcs.sbasize: %d bits" % ((sbcs >> 5) & 0x7F))
    print("sbcs.sbversion: %d" % ((sbcs >> 29) & 0x7))

    print("\nread x1")
    print("x1: 0x%08x" % target.read_gpr(1))

    print("\ncheck aarpostincrement")
    dm.write(DM_DATA0, 0)
    command = dm._access_register_control(csr.gpr_regno(1), postincrement=True)
    dm.write(DM_ABSTRACT_CMD, command)
    dm._wait_abstract()
    command = dm.read(DM_ABSTRACT_CMD)
    print("command_access_register: 0x%08x" % command)
    print("command_access_register.aarsize: %d" % ((command >> 20) & 0x7))
    print("command_access_register.aarpostincrement: %d" % ((command >> 19) & 1))
    print("command_access_register.regno: 0x%04x" % (command & 0xFFFF))
    if ((command >> 19) & 1) and (command & 0xFFFF) != csr.gpr_regno(2):
        print("aarpostincrement is not supported!")
    print("x1: 0x%08x" % dm.read(DM_DATA0))

    print("\nread misa")
    print("misa: 0x%08x" % target.read_csr(csr.CSR_MISA))

    print("\nread dpc")
    print("dpc: 0x%08x" % target.read_pc())


def test_quick_access(target):
    dm = target.dm
    hartinfo = dm.hartinfo_fields()
    progbufsize = (dm.read_abstractcs() >> 24) & 0x1F

    print("\nquick access")
    if progbufsize < 2:
        print("program buffer too small (%d words), skip" % progbufsize)
        return
    if hartinfo["dataaddr"] > 0x7FF and hartinfo["dataaccess"]:
        print("dataaddr 0x%x is out of sw offset range, skip" % hartinfo["dataaddr"])
        return

    # s0 = dpc; write s0 into data0 through the hart's memory/CSR map.
    dm.write(DM_PROG_BUF0, csrr(8, csr.CSR_DPC))
    if hartinfo["dataaccess"]:
        dm.write(DM_PROG_BUF0 + 1, sw(8, 0, hartinfo["dataaddr"]))
    else:
        dm.write(DM_PROG_BUF0 + 1, csrw(hartinfo["dataaddr"], 8))

    for index in range(6):
        try:
            value = dm.quick_access()
        except AbstractCommandError as error:
            print("quick access failed: %s" % error)
            break
        print("quick access %d dpc: 0x%08x" % (index, value))


def test_registers(target):
    print("\nregister write/read")
    original = target.read_gpr(5)
    target.write_gpr(5, 0x5A5A1234)
    value = target.read_gpr(5)
    print("x5: 0x%08x -> 0x%08x" % (original, value))
    target.write_gpr(5, original)

    print("\ncsr write/read (dscratch0)")
    original = target.read_csr(csr.CSR_DSCRATCH0)
    target.write_csr(csr.CSR_DSCRATCH0, 0x12345678)
    value = target.read_csr(csr.CSR_DSCRATCH0)
    print("dscratch0: 0x%08x -> 0x%08x" % (original, value))
    target.write_csr(csr.CSR_DSCRATCH0, original)

    print("\npriv: %d" % target.read_priv())


def test_memory(target):
    print("\naccess memory 0x%08x" % PROBE_MEM_ADDR)
    try:
        print("memory 0x%08x: 0x%08x" % (PROBE_MEM_ADDR, target.read_u32(PROBE_MEM_ADDR)))
    except Exception as error:
        print("memory read failed: %s" % error)

    if MEM_TEST_ADDR is None:
        print("memory write test skipped (set MEM_TEST_ADDR to a scratch RAM address)")
        return

    print("\nmemory write/read at 0x%08x" % MEM_TEST_ADDR)
    original = target.read_memory(MEM_TEST_ADDR, 4)
    target.write_memory(MEM_TEST_ADDR, b"\x78\x56\x34\x12")
    value = target.read_memory(MEM_TEST_ADDR, 4)
    print("memory: %s -> %s" % (original.hex(), value.hex()))
    target.write_memory(MEM_TEST_ADDR, original)


def test_triggers(target):
    print("\nprobe triggers")
    try:
        target.write_csr(csr.CSR_TSELECT, 0xFFFFFFFF)
        tselect_max = target.read_csr(csr.CSR_TSELECT)
        print("tselect_max: %d" % tselect_max)
        for index in range(tselect_max + 1):
            target.write_csr(csr.CSR_TSELECT, index)
            print("tselect: %d, tinfo: 0x%08x" % (index, target.read_csr(csr.CSR_TINFO)))
    except Exception as error:
        print("trigger probe failed: %s" % error)


def run_tests(target):
    print_dtm(target)
    test_debug_module(target)

    print("\nresume hart...")
    target.resume()
    time.sleep(0.05)
    print_dmstatus(target.dm)

    print("\nhalt hart...")
    target.halt()

    test_quick_access(target)
    test_registers(target)
    test_memory(target)
    test_triggers(target)

    print("\nresume hart...")
    target.resume()
    time.sleep(0.05)
    print_dmstatus(target.dm)


def open_target(protocol):
    taps = discover_taps(protocol)
    print("\nfound %d TAP(s)" % len(taps))
    for index, irlen in enumerate(taps):
        print("  TAP%d ir len: %d" % (index, irlen))

    for index, irlen in enumerate(taps):
        dtm = DTM(protocol, irlen=irlen)
        dtm.configure_tap(sum(taps[:index]), sum(taps[index + 1:]),
                          index, len(taps) - index - 1)
        target = RISCV(dtm=dtm)
        try:
            target.open()
        except Exception as error:
            print("TAP%d: %s" % (index, error))
            continue
        print("RISC-V DTM found at TAP%d" % index)
        return target

    raise RuntimeError("no RISC-V DTM found in the JTAG chain")


def main():
    itf = _get_interfaces()[0]
    itf.open()
    protocol = CMSISDAPProtocol(itf)
    target = None

    print("interface: %s" % itf)
    print("vendor: %s" % itf.vendor_name)
    print("product: %s" % itf.product_name)
    print("serial: %s" % itf.get_serial_number())

    try:
        print("capabilities: 0x%02x" % protocol.dap_info(DAPAccessIntf.ID.CAPABILITIES))
        protocol.connect(DAP_JTAG_PORT)
        protocol.set_swj_clock(1000000)

        target = open_target(protocol)
        run_tests(target)
    finally:
        if target is not None:
            try:
                target.close()
            except Exception:
                pass
        itf.close()


if __name__ == "__main__":
    main()
