#! python3
import cmd
import functools
import collections

from pyocd.probe import aggregator
from pyocd.coresight import dap, ap, cortex_m


class DAPCmdr(cmd.Cmd):
    prompt = 'DAPLink>'
    
    def __init__(self):
        super(DAPCmdr, self).__init__(self)

        print('DAPLink Commander v0.2\n'
              'blank line for connecting, ? for help\n'
              'address and value use hexadecimal, count use decimal\n')

        self.emptyline()

    def emptyline(self):
        daplinks = aggregator.DebugProbeAggregator.get_all_connected_probes()
        if not daplinks:
            print('no debug probe found\n')
            return

        for i in range(len(daplinks)):
            print(f'<{i}>: {daplinks[i].product_name}')
        print('')

        if len(daplinks) == 1:
            self.daplink = daplinks[0]
        else:
            while True:
                try:
                    n = int(input('input probe index >'))
                    if n >= len(daplinks): raise Exception()
                    break
                except Exception as e:
                    print(f'must be integer betwin 0 and {len(daplinks) - 1}')

            self.daplink = daplinks[n]
        
        try:
            self.daplink.open()

            _dp = dap.DebugPort(self.daplink, None)
            _dp.init()
            _dp.power_up_debug()

            _ap = ap.AHB_AP(_dp, 0)
            _ap.init()

            self.dap = cortex_m.CortexM(None, _ap)
            self.dap._read_core_type()

            print(f'IDCODE: 0x{_dp.dpidr:08X}')
            print(f'CPU core is {cortex_m.CORE_TYPE_NAME[self.dap.core_type]}\n')
        except Exception as e:
            print('no chip found\n')

    def connection_required(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                self.dap._read_core_type()
            except Exception as e:
                print('no connection established\n')
                return
            
            try:
                func(self, *args, **kwargs)
            except Exception as e:
                print('command argument error, please check!\n')
        return wrapper

    @connection_required
    def do_rd8(self, arg):
        '''Read  8-bit items. Syntax: rd8 <addr> <count>\n'''
        addr, cnt = arg.split()
        addr, cnt = int(addr, 16), int(cnt, 10)

        arr = []
        for i in range(cnt):
            arr.append(self.dap.read8(addr+i))

        print(''.join(['%02X, ' %x for x in arr]) + '\n')

    @connection_required
    def do_rd16(self, arg):
        '''Read 16-bit items. Syntax: rd16 <addr> <count>\n'''
        addr, cnt = arg.split()
        addr, cnt = int(addr, 16), int(cnt, 10)

        arr = []
        for i in range(cnt):
            arr.append(self.dap.read16(addr+i*2))

        print(''.join(['%04X, ' %x for x in arr]) + '\n')

    @connection_required
    def do_rd32(self, arg):
        '''Read 32-bit items. Syntax: rd32 <addr> <count>\n'''
        addr, cnt = arg.split()
        addr, cnt = int(addr, 16), int(cnt, 10)

        arr = []
        for i in range(cnt):
            arr.append(self.dap.read32(addr+i*4))

        print(''.join(['%08X, ' %x for x in arr]) + '\n')

    @connection_required
    def do_wr8(self, arg):
        '''Write  8-bit items. Syntax: wr8 <addr> <data>\n'''
        addr, data = arg.split()
        addr, data = int(addr, 16), int(data, 16)

        self.dap.write8(addr, data)

        print('\n')

    @connection_required
    def do_wr16(self, arg):
        '''Write 16-bit items. Syntax: wr16 <addr> <data>\n'''
        addr, data = arg.split()
        addr, data = int(addr, 16), int(data, 16)

        self.dap.write16(addr, data)

        print('\n')

    @connection_required
    def do_wr32(self, arg):
        '''Write 32-bit items. Syntax: wr32 <addr> <data>\n'''
        addr, data = arg.split()
        addr, data = int(addr, 16), int(data, 16)

        self.dap.write32(addr, data)

        print('\n')

    @connection_required
    def do_loadbin(self, arg):
        '''Load *.bin file into target memory.
Syntax: loadbin <filename> <addr>\n'''
        file, addr = arg.split()
        addr = int(addr, 16)

        with open(file, 'rb') as f:
            data = [ord(x) for x in f.read()]

            self.dap.write_memory_block8(addr, data)

        print('\n')

    @connection_required
    def do_savebin(self, arg):
        '''Saves target memory into binary file.
Syntax: savebin <filename> <addr> <NumBytes>\n'''
        file, addr, cnt = arg.split()
        addr, cnt = int(addr, 16), int(cnt, 10)

        with open(file, 'wb') as f:
            data = self.dap.read_memory_block8(addr, cnt)

            f.write(''.join([chr(x) for x in data]))

        print('\n')

    @connection_required
    def do_regs(self, arg):
        '''Display contents of registers
Can only exec when Core halted\n'''
        vals = self.dap.read_core_registers_raw(range(17))

        s = ''
        for i in range(16):
            s += 'r%-2d: %08X, ' %(i, vals[i])

            if i % 4 == 3: s += '\n'
        s += 'xpsr: %08X\n' %vals[16]

        print(s)

    @connection_required
    def do_wreg(self, arg):
        '''Write register. Syntax: wreg <RegName> <Value>
Can only exec when Core halted\n'''
        reg, value = arg.split()
        value = int(value, 16)
        
        self.dap.write_core_register_raw(reg, value)

        print('\n')

    @connection_required
    def do_reset(self, arg):
        '''reset core\n'''
        self.dap.reset()

        print('\n')

    @connection_required
    def do_halt(self, arg):
        '''halt core\n'''
        self.dap.halt()

        self.do_regs('')

    @connection_required
    def do_go(self, arg):
        '''resume core\n'''
        self.dap.resume()

        print('\n')


if __name__ == '__main__':
    cmd = DAPCmdr()
    cmd.cmdloop()
