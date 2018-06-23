"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2006-2013 ARM Limited
"""

import os
import logging

from hidapi_backend import HidApiUSB
from pyusb_backend import PyUSB
from pywinusb_backend import PyWinUSB

INTERFACE = {
             'hidapiusb': HidApiUSB,
             'pyusb': PyUSB,
             'pywinusb': PyWinUSB,
            }

# Allow user to override backend with an environment variable.
usb_backend = os.getenv('PYOCD_USB_BACKEND', "")

# Check validity of backend env var.
if usb_backend and ((usb_backend not in INTERFACE.keys()) or (not INTERFACE[usb_backend].isAvailable)):
    logging.error("Invalid USB backend specified in PYOCD_USB_BACKEND: " + usb_backend)
    usb_backend = ""

# Select backend based on OS and availability.
if not usb_backend:
    if os.name == "nt":
        # Prefer hidapi over pyWinUSB for Windows, since pyWinUSB has known bug(s)
        if HidApiUSB.isAvailable:
            usb_backend = "hidapiusb"
        elif PyWinUSB.isAvailable:
            usb_backend = "pywinusb"
        else:
            raise Exception("No USB backend found")
    elif os.name == "posix":
        # Select hidapi for OS X and pyUSB for Linux.
        if os.uname()[0] == 'Darwin':
            usb_backend = "hidapiusb"
        else:
            usb_backend = "pyusb"
    else:
        raise Exception("No USB backend found")

