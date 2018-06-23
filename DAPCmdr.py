#! C:\Python27\python.exe
#coding: gbk
import os
import re
import sys
import cmd
import struct

from daplink import coresight
from daplink import pyDAPAccess


class DAPCmdr(cmd.Cmd):
    prompt = 'DAPLink>'
    intro  = '''DAPLink Commander v0.1
空行回车连接单片机；'?' 回车显示帮助
命令参数说明：地址和数据都用十六进制，个数用十进制
'''

    def emptyline(self):
        self.daplink = pyDAPAccess.DAPAccess.get_connected_devices()[0]
        self.daplink.open()

        self.dp = coresight.dap.DebugPort(self.daplink)
        self.dp.init()
        self.dp.power_up_debug()

        self.ap = coresight.ap.AHB_AP(self.dp, 0)
        self.ap.init()

        self.cpu = coresight.cortex_m.CortexM(self.daplink, self.dp, self.ap)
        self.cpu.readCoreType()

        print 'IDCODE: 0x%08X' %self.dp.dpidr
        print 'CPU core is %s' %coresight.cortex_m.CORE_TYPE_NAME[self.cpu.core], '\n'

    def do_rd8(self, arg):
        '''Read  8-bit items. Syntax: rd8 <addr> <count>\n'''
        addr, cnt = arg.split()
        addr, cnt = int(addr, 16), int(cnt, 10)

        arr = []
        for i in range(cnt):
            arr.append(self.ap.read8(addr+i))

        print ''.join(['%02X, ' %x for x in arr]) + '\n'

    def do_rd16(self, arg):
        '''Read 16-bit items. Syntax: rd16 <addr> <count>\n'''
        addr, cnt = arg.split()
        addr, cnt = int(addr, 16), int(cnt, 10)

        arr = []
        for i in range(cnt):
            arr.append(self.ap.read16(addr+i*2))

        print ''.join(['%04X, ' %x for x in arr]) + '\n'

    def do_rd32(self, arg):
        '''Read 32-bit items. Syntax: rd32 <addr> <count>\n'''
        addr, cnt = arg.split()
        addr, cnt = int(addr, 16), int(cnt, 10)

        arr = []
        for i in range(cnt):
            arr.append(self.ap.read32(addr+i*4))

        print ''.join(['%08X, ' %x for x in arr]) + '\n'

    def do_wr8(self, arg):
        '''Write  8-bit items. Syntax: wr8 <addr> <data>\n'''
        addr, data = arg.split()
        addr, data = int(addr, 16), int(data, 16)

        self.ap.write8(addr, data)

        print '\n'

    def do_wr16(self, arg):
        '''Write 16-bit items. Syntax: wr16 <addr> <data>\n'''
        addr, data = arg.split()
        addr, data = int(addr, 16), int(data, 16)

        self.ap.write16(addr, data)

        print '\n'

    def do_wr32(self, arg):
        '''Write 32-bit items. Syntax: wr32 <addr> <data>\n'''
        addr, data = arg.split()
        addr, data = int(addr, 16), int(data, 16)

        self.ap.write32(addr, data)

        print '\n'

    def do_loadbin(self, arg):
        '''Load *.bin file into target memory.
Syntax: loadfile <filename> <addr>\n'''
        file, addr = arg.split()
        addr = int(addr, 16)

        with open(file, 'rb') as f:
            data = [ord(x) for x in f.read()]

            self.ap.writeBlockMemoryUnaligned8(addr, data)

        print '\n'

    def do_savebin(self, arg):
        '''Saves target memory into binary file.
Syntax: savebin <filename> <addr> <NumBytes>\n'''
        file, addr, cnt = arg.split()
        addr, cnt = int(addr, 16), int(cnt, 10)

        with open(file, 'wb') as f:
            data = self.ap.readBlockMemoryUnaligned8(addr, cnt)

            f.write(''.join([chr(x) for x in data]))

        print '\n'

    def do_regs(self, arg):
        '''Display contents of registers
Can only exec when Core halted\n'''
        vals = self.cpu.readCoreRegistersRaw(range(17))

        s = ''
        for i in range(16):
            s += 'r%-2d: %08X, ' %(i, vals[i])

            if i % 4 == 3: s += '\n'
        s += 'xpsr: %08X\n' %vals[16]

        print s

    def do_wreg(self, arg):
        '''Write register. Syntax: wreg <RegName> <Value>
Can only exec when Core halted\n'''
        reg, value = arg.split()
        value = int(value, 16)
        
        self.cpu.writeCoreRegister(reg, value)

        print '\n'

    def do_reset(self, arg):
        '''reset core\n'''
        self.cpu.reset()

        print '\n'

    def do_halt(self, arg):
        '''halt core\n'''
        self.cpu.halt()

        self.do_regs('')

    def do_go(self, arg):
        '''resume core\n'''
        self.cpu.resume()

        print '\n'


if __name__ == '__main__':
    DAPCmdr().cmdloop()
