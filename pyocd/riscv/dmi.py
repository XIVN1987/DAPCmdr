"""Debug Module Interface (DMI) transactions with busy/error handling."""

from .dtm import (DMI_OP_NOP, DMI_OP_READ, DMI_OP_WRITE,
                  DMI_STATUS_BUSY, DMI_STATUS_SUCCESS)


class DMIError(Exception):
    """Raised when a DMI transaction fails or stays busy."""


class DMI(object):
    """Reliable DMI reads and writes on top of the raw DTM interface."""

    def __init__(self, dtm, retries=6):
        self.dtm = dtm
        self.retries = retries

    def nop(self):
        """Perform a NOP transaction and return its DMI status."""
        _, status = self.dtm.dmi(0, 0, DMI_OP_NOP)
        return status

    def read(self, addr):
        """Read a 32-bit debug module register."""
        self.dtm.dmi(addr, 0, DMI_OP_READ)

        data = 0
        status = DMI_STATUS_BUSY
        for _ in range(self.retries + 1):
            data, status = self.dtm.dmi(0, 0, DMI_OP_NOP)
            if status != DMI_STATUS_BUSY:
                break

        if status != DMI_STATUS_SUCCESS:
            self.dtm.dmi_reset()
            raise DMIError("DMI read of 0x%02x failed (status %d)" % (addr, status))
        return data

    def write(self, addr, value):
        """Write a 32-bit debug module register."""
        self.dtm.dmi(addr, value & 0xFFFFFFFF, DMI_OP_WRITE)

        status = DMI_STATUS_BUSY
        for _ in range(self.retries + 1):
            _, status = self.dtm.dmi(0, 0, DMI_OP_NOP)
            if status != DMI_STATUS_BUSY:
                break

        if status != DMI_STATUS_SUCCESS:
            self.dtm.dmi_reset()
            raise DMIError("DMI write of 0x%02x failed (status %d)" % (addr, status))
