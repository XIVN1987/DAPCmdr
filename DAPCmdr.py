#!python3
import os
import re
import sys
import ptkcmd
import functools
import configparser
from prompt_toolkit.completion import Completion
from prompt_toolkit.shortcuts import yes_no_dialog

import jlink
import xlink
import svd
import hardfault
import callstack

#sys.path.append(sys.exec_prefix + r'\vexe\Lib\site-packages')
#import ipdb


os.environ['PATH'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libusb-1.0.24/MinGW64/dll') + os.pathsep + os.environ['PATH']


class DAPCmdr(ptkcmd.PtkCmd):
    prompt = 'DAPCmdr > '
    intro = '''J-Link and DAPLink Commander v0.7
blank line for connection, ? for help
address and value use hexadecimal, count use decimal\n'''
    
    def __init__(self):
        super(DAPCmdr, self).__init__(self)

        self.initSetting()

        self.env = {
            '%pwd%':  os.getcwd(),
            '%home%': os.path.expanduser('~')
        }
        self.env.update(self.get_MDK_Packs_path())
        
    def initSetting(self):
        if not os.path.exists('setting.ini'):
            open('setting.ini', 'w')
        
        self.conf = configparser.ConfigParser()
        self.conf.read('setting.ini', encoding='utf-8')

        if not self.conf.has_section('paths'):
            self.conf.add_section('paths')
            self.conf.set('paths', 'dllpath', r'C:\Segger\JLink_V692\JLink_x64.dll')
            self.conf.set('paths', 'svdpath', r'["C:\Keil_v5\ARM\Packs\Keil\STM32F1xx_DFP\2.3.0\SVD\STM32F103xx.svd"]')
            self.conf.set('paths', 'dispath', r'["D:\Project\STM32_Blinky\out\STM32_Blinky.axf"]')
            self.conf.write(open('setting.ini', 'w', encoding='utf-8'))

        self.svdpaths = eval(self.conf.get('paths', 'svdpath'))
        self.dispaths = eval(self.conf.get('paths', 'dispath'))

        self.dllpath = self.conf.get('paths', 'dllpath')
        self.svdpath = self.svdpaths[0]
        self.dispath = self.dispaths[0]

        if os.path.isfile(self.svdpath):
            self.dev = svd.SVD(self.svdpath).device

            self.mcucore = self.dev.cpu.name

        else:
            self.mcucore = 'Cortex-M0'

    def preloop(self):
        self.onecmd('path')

        self.xlk = None
        self.onecmd('')

    def emptyline(self):     
        try:
            if self.xlk == None:
                try:
                    from pyocd.probe import aggregator
                    from pyocd.coresight import dap, ap, cortex_m
                    daplinks = aggregator.DebugProbeAggregator.get_all_connected_probes()
                except Exception as e:
                    daplinks = []

                if daplinks and os.path.isfile(self.dllpath):
                    use_dap = yes_no_dialog(title='J-Link or DAPLink', text=f'Do you want to use {daplinks[0].product_name}?').run()

                elif os.path.isfile(self.dllpath):
                    use_dap = False

                elif daplinks:
                    use_dap = True

                else:
                    raise Exception('No link found')

                if use_dap:
                    daplink = daplinks[0]
                    daplink.open()

                    _dp = dap.DebugPort(daplink, None)
                    _dp.init()
                    _dp.power_up_debug()

                    _ap = ap.AHB_AP(_dp, 0)
                    _ap.init()

                    self.xlk = xlink.XLink(cortex_m.CortexM(None, _ap))

                else:
                    self.xlk = xlink.XLink(jlink.JLink(self.dllpath, self.mcucore))

            else:
                self.xlk.close()
                self.xlk.open(self.mcucore)
            
            print(f'CPU core is {self.xlk.read_core_type()}\n')
        except Exception as e:
            print('connection fail\n')
            self.xlk = None

    def connection_required(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                self.xlk.read_core_type()
            except Exception as e:
                print('no connection established\n')
                self.xlk = None
                return
            
            try:
                func(self, *args, **kwargs)
            except Exception as e:
                print('command argument error, please check!\n')
        return wrapper

    @connection_required
    def do_rd8(self, addr, cnt):
        '''Read  8-bit items. Syntax: rd8 <addr> <count>\n'''
        addr, cnt = int(addr, 16), int(cnt, 10)

        arr = self.xlk.read_mem_U8(addr, cnt)

        print(''.join(['%02X, ' %x for x in arr]) + '\n')

    @connection_required
    def do_rd16(self, addr, cnt):
        '''Read 16-bit items. Syntax: rd16 <addr> <count>\n'''
        addr, cnt = int(addr, 16), int(cnt, 10)

        arr = self.xlk.read_mem_U16(addr, cnt)

        print(''.join(['%04X, ' %x for x in arr]) + '\n')

    @connection_required
    def do_rd32(self, addr, cnt):
        '''Read 32-bit items. Syntax: rd32 <addr> <count>\n'''
        addr, cnt = int(addr, 16), int(cnt, 10)

        arr = self.xlk.read_mem_U32(addr, cnt)

        print(''.join(['%08X, ' %x for x in arr]) + '\n')

    @connection_required
    def do_wr8(self, addr, val):
        '''Write  8-bit items. Syntax: wr8 <addr> <value>\n'''
        addr, val = int(addr, 16), int(val, 16)

        self.xlk.write_U8(addr, val)

        print()

    @connection_required
    def do_wr16(self, addr, val):
        '''Write 16-bit items. Syntax: wr16 <addr> <value>\n'''
        addr, val = int(addr, 16), int(val, 16)

        self.xlk.write_U16(addr, val)

        print()

    @connection_required
    def do_wr32(self, addr, val):
        '''Write 32-bit items. Syntax: wr32 <addr> <value>\n'''
        addr, val = int(addr, 16), int(val, 16)

        self.xlk.write_U32(addr, val)

        print()

    @connection_required
    def do_loadbin(self, file, addr):
        '''Load binary file into target memory.
Syntax: loadbin <filepath> <addr>\n'''
        addr = int(addr, 16)

        with open(file, 'rb') as f:
            data = f.read()

            self.xlk.write_mem(addr, data)

        print()

    @connection_required
    def do_savebin(self, file, addr, cnt):
        '''Save target memory into binary file.
Syntax: savebin <filepath> <addr> <NumBytes>\n'''
        addr, cnt = int(addr, 16), int(cnt, 10)

        with open(file, 'wb') as f:
            data = self.xlk.read_mem_U8(addr, cnt)

            f.write(bytes(data))

        print()

    @connection_required
    def do_regs(self):
        '''Display core registers value. Syntax: regs
Can only exec when Core halted\n'''
        if not self.xlk.halted():
            print('should halt first!\n')
            return

        regs = ['R0', 'R1', 'R2',  'R3',  'R4',  'R5', 'R6', 'R7',
                'R8', 'R9', 'R10', 'R11', 'R12', 'SP', 'LR', 'PC',
                'MSP', 'PSP', 'XPSR', 'CONTROL'
        ]
        vals = self.xlk.read_regs(regs)
        vals['CONTROL'] >>= 24  # J-Link Control Panel 中显示的也是移位前的

        print('R0 : %08X    R1 : %08X    R2 : %08X    R3 : %08X\n'
              'R4 : %08X    R5 : %08X    R6 : %08X    R7 : %08X\n'
              'R8 : %08X    R9 : %08X    R10: %08X    R11: %08X\n'
              'R12: %08X    SP : %08X    LR : %08X    PC : %08X\n'
              'MSP: %08X    PSP: %08X    XPSR: %08X\n'
              'CONTROL: %02X (when Thread mode: %s, use %s)\n'
            %(vals['R0'],   vals['R1'],  vals['R2'],  vals['R3'],
              vals['R4'],   vals['R5'],  vals['R6'],  vals['R7'],
              vals['R8'],   vals['R9'],  vals['R10'], vals['R11'],
              vals['R12'],  vals['SP'],  vals['LR'],  vals['PC'],
              vals['MSP'],  vals['PSP'], vals['XPSR'],
              vals['CONTROL'], 'unprivileged' if vals['CONTROL']&1 else 'privileged', 'PSP' if vals['CONTROL']&2 else 'MSP',
             ))

        if vals['XPSR'] & 0xFF in (3, 12):
            if self.xlk.read_core_type() not in ['Cortex-M0', 'Cortex-M0+']:
                causes = hardfault.diagnosis(self.xlk)
                print("\n".join(causes))

            if (vals['LR'] >> 2) & 1 == 0:
                fault_SP = vals['MSP']  # 发生HardFault时使用的栈，也就是HardFault异常栈帧所在的栈
            else:
                fault_SP = vals['PSP']

            stackMem = self.xlk.read_mem_U32(fault_SP, 64)  # 读取个数须是8的整数倍

            print(f'\nStack Content @ 0x{fault_SP:08X}:')
            for i in range(len(stackMem) // 8):
                print(f'{fault_SP+i*8*4:08X}:  {stackMem[i*8]:08X} {stackMem[i*8+1]:08X} {stackMem[i*8+2]:08X} {stackMem[i*8+3]:08X} {stackMem[i*8+4]:08X} {stackMem[i*8+5]:08X} {stackMem[i*8+6]:08X} {stackMem[i*8+7]:08X}')
            
            if os.path.isfile(self.dispath):
                cs = callstack.CallStack(self.dispath)
                if cs.Functions:
                    print(f'\n{cs.parseStack(stackMem)}\n')
    
    @connection_required
    def do_wreg(self, reg, val):
        '''Write core register. Syntax: wreg <RegName> <value>
Can only exec when Core halted\n'''
        if not self.xlk.halted():
            print('should halt first!\n')
            return

        val = int(val, 16)
        
        self.xlk.write_reg(reg, val)

        print()

    @connection_required
    def do_reset(self):
        '''reset core\n'''
        self.xlk.reset()

        print()

    @connection_required
    def do_halt(self):
        '''halt core\n'''
        self.xlk.halt()

        self.do_regs()

    @connection_required
    def do_go(self):
        '''resume core\n'''
        self.xlk.go()

        print()

    def do_path(self, subcmd=None, *path):
        '''display path, Syntax: path
set JLink_x64.dll, Syntax: path dll <dllpath>
set svd file path, Syntax: path svd <svdpath>
set dis file path, Syntax: path dis <dispath>\n'''
        if subcmd == None:
            maxlen = max(len(self.dllpath), len(self.svdpath), len(self.dispath))
            print(f'{"√" if os.path.isfile(self.dllpath) else "×"}  {self.dllpath:{maxlen}}')
            print(f'{"√" if os.path.isfile(self.svdpath) else "×"}  {self.svdpath:{maxlen}}')
            print(f'{"√" if os.path.isfile(self.dispath) else "×"}  {self.dispath:{maxlen}}\n')

        else:
            if path:
                path = ' '.join(path)
                match = re.match(r'%\w+%', path)
                if match:
                    path = path.replace(match.group(0), self.env[match.group(0)])

                if os.path.isfile(path):  # return True if path is an existing regular file
                    if subcmd == 'dll':
                        self.dllpath = path

                    elif subcmd == 'svd':
                        self.svdpath = path

                        self.dev = svd.SVD(self.svdpath).device
                        self.mcucore = self.dev.cpu.name

                    elif subcmd == 'dis':
                        self.dispath = path

                    else:
                        print(f'{subcmd} Unknown\n')

                    self.saveSetting()

                else:
                    print('Not exists or Not file\n')

            else:
                print('Input error\n')

    def complete_path(self, pre_args, curr_arg, document, complete_event):
        if len(pre_args) > 0:
            if pre_args[0] == 'dll':   extra_paths =[self.dllpath]
            elif pre_args[0] == 'svd': extra_paths = self.svdpaths
            elif pre_args[0] == 'dis': extra_paths = self.dispaths
            else: return
            
            yield from ptkcmd.complete_path(' '.join([*pre_args[1:], curr_arg]), extra_paths, self.env)

    @connection_required
    def do_sv(self, input, val=None):
        '''svd-based peripheral register read and write
register read:        sv <peripheral>.<register>
register write:       sv <peripheral>.<register> <hex>
register field write: sv <peripheral>.<register>.<field> <dec>\n'''
        obj = self.dev
        for name in input.split('.'):
            match = re.match(r'(\w+)\[(\d+)\]', name)

            name = re.sub(r'(\w+)\[\d+\]', r'\1', name)
            if name in obj.children:
                obj = obj.children[name]

                if isinstance(obj, svd.Peripheral): peri = obj

                if match and isinstance(obj, svd.RegisterArray):
                    index = int(match.group(2))
                    if index < len(obj):
                        obj = obj[index]
                    else:
                        print('index Overflow\n')
                        return

            else:
                print(f'{name} Unknown\n')
                return

        if val == None:
            if isinstance(obj, svd.Peripheral) or isinstance(obj, svd.Cluster):
                addr, count = obj.addr, obj.nwrd

            elif isinstance(obj, svd.RegisterArray):
                addr, count = obj.addr, len(obj)

            else:
                addr, count = obj.addr, 1

            if not isinstance(obj, svd.Peripheral):
                addr += peri.addr

            if count > 128:
                print('Too much to read\n')
                return
            
            values = self.xlk.read_mem_U32(addr, count)
            obj.load_value({addr-peri.addr+i*4: val for i, val in enumerate(values)})

            print(obj)

        else:
            addr = peri.addr + obj.addr

            if isinstance(obj, svd.Register):
                try:
                    val = int(val, 16)
                except Exception as e:
                    print(f'{val} is not valid hexadecimal\n')
                    return

                self.xlk.write_U32(addr, val)

            elif isinstance(obj, svd.Field):
                try:
                    val = int(val, 10)
                except Exception as e:
                    print(f'{val} is not valid decimal\n')
                    return

                value = self.xlk.read_U32(addr)
                value = value & (~obj.mask) | (val << obj.pos)
                self.xlk.write_U32(addr, value)

            else:
                print('Can only write register and field\n')

    def complete_sv(self, pre_args, curr_arg, document, complete_event):
        if len(pre_args) == 0 and curr_arg:
            obj = self.dev
            names = curr_arg.split('.')
            for name in names[:-1]:
                match = re.match(r'(\w+)\[(\d+)\]', name)

                name = re.sub(r'(\w+)\[\d+\]', r'\1', name)
                if name in obj.children:
                    obj = obj.children[name]

                    if match and isinstance(obj, svd.RegisterArray):
                        index = int(match.group(2))
                        if index < len(obj):
                            obj = obj[index]
                        else:
                            return

                    if isinstance(obj, svd.RegisterArray):
                        return

                else:
                    return

            yield from [Completion(name, -len(names[-1])) for name in ptkcmd.fuzzy_match(names[-1], obj.children.keys(), sort=False)]
    
    @connection_required
    def do_dis(self):
        '''display CallStack information coming from disassembling file.

disassembling file can be built by command below:
MDK: fromelf --text -a -c -o "$L@L.dis" "#L"
IAR: ielfdumparm --code --source $TARGET_PATH$ -o $TARGET_PATH$.dis
GCC: objdump -d $@ > $@.dis\n'''
        if os.path.isfile(self.dispath):
            cs = callstack.CallStack(self.dispath)
            if cs.Functions:
                print(f'{cs}\n')

            else:
                print("disassembling file parse Fail\n")

        else:
            print("disassembling file Not Exists\n")

    def do_env(self):
        '''display enviriment variables\n'''
        for key, val in self.env.items():
            print(f'{key:<10s}{val}')
        print()

    def get_MDK_Packs_path(self):
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r'UVPROJXFILE\Shell\open\command')
            val = winreg.QueryValue(key, '')
            key.Close()
            
            # "C:\Programs\uVision\UV4\UV4.exe" "%1"
            match = re.match(r'"(.+?)\\UV4\\UV4.exe"', val)
            if match:
                MDK_path = match.group(1)

                conf = configparser.ConfigParser()
                conf.read(os.path.join(MDK_path, 'TOOLS.INI'), encoding='gbk')
                Packs_path = conf.get('UV2', 'RTEPATH')[1:-1]
                if os.path.exists(Packs_path):
                    return {'%Packs%': Packs_path}

        except:
            return {}

    def saveSetting(self):
        self.conf.set('paths', 'dllpath', self.dllpath)

        if self.svdpath in self.svdpaths:
            self.svdpaths.remove(self.svdpath)
        self.svdpaths.insert(0, self.svdpath)
        self.conf.set('paths', 'svdpath', repr(self.svdpaths[:10]))

        if self.dispath in self.dispaths:
            self.dispaths.remove(self.dispath)
        self.dispaths.insert(0, self.dispath)
        self.conf.set('paths', 'dispath', repr(self.dispaths[:10]))

        self.conf.write(open('setting.ini', 'w', encoding='utf-8'))


#with ipdb.launch_ipdb_on_exception():
if __name__ == '__main__':
    cmd = DAPCmdr()
    cmd.cmdloop()
