"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2006-2013 ARM Limited
"""
from .dap_access_api import DAPAccessIntf
from .dap_access_cmsis_dap import DAPAccessCMSISDAP

# alias DAPAccessCMSISDAP as main DAPAccess class
DAPAccess = DAPAccessCMSISDAP
