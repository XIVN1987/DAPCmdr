# DAPCmdr
J-LINK Commander like tool for DAPLink (CMSIS-DAP)

To run this tool, you need python 3.6 and a usb backend (hidapi or pywinusb for windows, pyusb for linux, hidapi for mac)

![](https://github.com/XIVN1987/DAPCmdr/blob/master/截屏.jpg)

Note: the software uses the following statement to find the debugger
``` python 
if product_name.find("CMSIS-DAP") < 0:
    # Skip non cmsis-dap HID device
```
