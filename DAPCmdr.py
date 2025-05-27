#!python3
import os
import re
import sys
import struct
import ptkcmd
import functools
import collections
import configparser
from prompt_toolkit.completion import Completion
from prompt_toolkit.shortcuts import radiolist_dialog

import jlink
import xlink
import svd
import hardfault
import callstack

#sys.path.append(sys.exec_prefix + r'\vexe\Lib\site-packages')
#import ipdb


os.environ['PATH'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libusb-1.0.24/MinGW64/dll') + os.pathsep + os.environ['PATH']


Variable = collections.namedtuple('Variable', 'name addr size')     # variable from *.elf file


class DAPCmdr(ptkcmd.PtkCmd):
    prompt = 'DAPCmdr > '
    intro = '''J-Link and DAPLink Commander v0.9
blank line for connection, ? for help
address and value use hexadecimal, count use decimal\n'''
    
    def __init__(self):
        super(DAPCmdr, self).__init__(self)

        self.initSetting()

        self.elfinfo = ()

        self.Vars = {}

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

        if not self.conf.has_section('link'):
            self.conf.add_section('link')
            self.conf.set('link', 'mode', 'arm')
            self.conf.set('link', 'speed', '4 MHz')
            self.conf.write(open('setting.ini', 'w', encoding='utf-8'))

        self.mode = self.conf.get('link', 'mode')
        self.speed = int(self.conf.get('link', 'speed').split()[0])

        if not self.conf.has_section('paths'):
            self.conf.add_section('paths')
            self.conf.set('paths', 'dllpath', r'C:\Segger\JLink_V692\JLink_x64.dll')
            self.conf.set('paths', 'svdpath', r'["C:\Keil_v5\ARM\Packs\Keil\STM32F1xx_DFP\2.3.0\SVD\STM32F103xx.svd"]')
            self.conf.set('paths', 'elfpath', r'["D:\Project\STM32_Blinky\out\STM32_Blinky.axf"]')
            self.conf.write(open('setting.ini', 'w', encoding='utf-8'))

        self.svdpaths = eval(self.conf.get('paths', 'svdpath'))
        self.elfpaths = eval(self.conf.get('paths', 'elfpath'))

        self.dllpath = self.conf.get('paths', 'dllpath')
        self.svdpath = self.svdpaths[0]
        self.elfpath = self.elfpaths[0]

        if os.path.isfile(self.svdpath):
            self.svdev = svd.SVD(self.svdpath).device

    def device_core(self):
        if self.mode.startswith('arm'):
            core = 'Cortex-M0'
        else:
            core = 'RISC-V'

        if self.mode.startswith('arm') and hasattr(self, 'svdev'):
            core = self.svdev.cpu.name

        return core

    def preloop(self):
        self.onecmd('path')

        self.xlk = None
        self.onecmd('')

    def emptyline(self):
        print(f'mode = {self.mode}, speed = {self.speed}MHz\n')

        try:
            if self.xlk == None:
                try:
                    from pyocd.probe import aggregator
                    from pyocd.coresight import dap, ap, cortex_m
                    daplinks = aggregator.DebugProbeAggregator.get_all_connected_probes()
                except Exception as e:
                    daplinks = []

                if daplinks and os.path.isfile(self.dllpath) or len(daplinks) > 1:
                    values = [(0, 'J-Link')] + [(i+1, f'{lnk.product_name} ({lnk.unique_id})') for i, lnk in enumerate(daplinks)]
                    index = radiolist_dialog(title="probe select", text="Which probe would you like ?", values=values).run()

                elif os.path.isfile(self.dllpath):
                    index = 0

                elif daplinks:
                    index = 1

                else:
                    raise Exception('No link found')

                if index:
                    daplink = daplinks[index-1]
                    daplink.open()

                    _dp = dap.DebugPort(daplink, None)
                    _dp.init()
                    _dp.power_up_debug()
                    _dp.set_clock(self.speed * 1000000)

                    _ap = ap.AHB_AP(_dp, 0)
                    _ap.init()

                    self.xlk = xlink.XLink(cortex_m.CortexM(None, _ap))

                else:
                    self.xlk = xlink.XLink(jlink.JLink(self.dllpath, self.mode, self.device_core(), self.speed * 1000))

            else:
                self.xlk.close()
                self.xlk.open(self.mode, self.device_core(), self.speed * 1000)
            
            print(f'CPU core is {self.xlk.read_core_type()}\n')
        except Exception as e:
            print('connection fail\n')
            self.xlk = None

    def do_mode(self, mode):
        '''Set link mode. Syntax: mode arm/armj/rv/rvj\n'''
        if mode in ('arm', 'armj', 'rv', 'rvj'):
            self.mode = mode

            self.saveSetting()

        else:
            print('can only be arm, armj, rv or rvj\n')

    def do_speed(self, speed):
        '''Set link speed in MHz. Syntax: speed <speed>\n'''
        try:
            self.speed = int(speed)

            self.saveSetting()

        except Exception as e:
            print('<speed> can only be integer\n')

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
    def do_rdv(self, name, fmt='i'):
        '''Read variable. Syntax: rdv <variable> [i/u/f/h]\n'''
        if name in self.Vars:
            var = self.Vars[name]
        else:
            print('unknown variable')
            return

        if var.size == 1:
            val = self.xlk.read_mem_U8(var.addr, 1)[0]
            if fmt == 'i':
                val = struct.unpack('b', struct.pack('B', val))[0]

        elif var.size == 2:
            val = self.xlk.read_mem_U16(var.addr, 1)[0]
            if fmt == 'i':
                val = struct.unpack('h', struct.pack('H', val))[0]

        elif var.size == 4:
            val = self.xlk.read_mem_U32(var.addr, 1)[0]
            if fmt == 'i':
                val = struct.unpack('i', struct.pack('I', val))[0]
            elif fmt == 'f':
                val = struct.unpack('f', struct.pack('I', val))[0]

        elif var.size == 8:
            val = self.xlk.read_mem_U32(var.addr, 2)
            val = (val[1] << 32) | val[0]
            if fmt == 'i':
                val = struct.unpack('i', struct.pack('I', val))[0]
            elif fmt == 'f':
                val = struct.unpack('d', struct.pack('I', val))[0]

        if fmt == 'h':
            print(f'0x{val:0{var.size}X}')
        else:
            print(val)

    @connection_required
    def do_wrv(self, name, val):
        '''Write variable. Syntax: wrv <variable> <value>\n'''
        if name in self.Vars:
            var = self.Vars[name]
        else:
            print('unknown variable')
            return

        try:
            val = int(val)
        except:
            try:
                val = int(val, 16)
            except:
                try:
                    val = float(val)
                except:
                    print('invalid value')
                    return

        if var.size == 1:
            self.xlk.write_U8(var.addr, val)

        elif var.size == 2:
            self.xlk.write_U16(var.addr, val)

        elif var.size == 4:
            if isinstance(val, float):
                val = struct.unpack('I', struct.pack('f', val))[0]
            
            self.xlk.write_U32(var.addr, val)

        elif var.size == 8:
            if isinstance(val, float):
                val = struct.unpack('I', struct.pack('d', val))[0]

            self.xlk.write_U32(var.addr, val & 0xFFFFFFFF)
            self.xlk.write_U32(var.addr, val >> 32)
        
        print()

    def complete_rdv(self, pre_args, curr_arg, document, complete_event):
        if len(pre_args) == 0 and curr_arg:
            if os.path.exists(self.elfpath):
                if self.elfinfo != (self.elfpath, os.path.getmtime(self.elfpath)):
                    self.elfinfo = (self.elfpath, os.path.getmtime(self.elfpath))
                    self.Vars = {}
                    try:
                        from elftools.elf.elffile import ELFFile
                        elffile = ELFFile(open(self.elfpath, 'rb'))

                        for sym in elffile.get_section_by_name('.symtab').iter_symbols():
                            if sym.entry['st_info']['type'] == 'STT_OBJECT' and sym.entry['st_size'] in (1, 2, 4, 8):
                                self.Vars[sym.name] = Variable(sym.name, sym.entry['st_value'], sym.entry['st_size'])
                        
                    except Exception as e:
                        print(f'\nparse elf file fail: {e}')

            else:
                print('\nto access variable, must ensure elf file exists')

            yield from [Completion(name, -len(curr_arg)) for name in ptkcmd.fuzzy_match(curr_arg, self.Vars.keys(), sort=False)]

    def complete_wrv(self, pre_args, curr_arg, document, complete_event):
        yield from self.complete_rdv(pre_args, curr_arg, document, complete_event)

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

        if self.mode.startswith('arm'):
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
                
                if os.path.isfile(self.elfpath):
                    cs = callstack.CallStack(self.elfpath)
                    if cs.Functions:
                        print(f'\n{cs.parseStack(stackMem, causes)}\n')

        elif self.mode.startswith('rv'):
            regs = ['pc', 'ra', 'sp', 'gp', 'tp', 'fp', 't0', 't1',
                    't2', 't3', 't4', 't5', 't6', 'a0', 'a1', 'a2',
                    'a3', 'a4', 'a5', 'a6', 'a7', 's0', 's1', 's2',
                    's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11'
            ]
            vals = self.xlk.read_regs(regs)

            print('pc : %08X    ra : %08X    sp : %08X\n'
                  'gp : %08X    tp : %08X    fp : %08X\n'
                  't0 : %08X    t1 : %08X    t2 : %08X\n'
                  't3 : %08X    t4 : %08X    t5 : %08X    t6 : %08X\n'
                  'a0 : %08X    a1 : %08X    a2 : %08X    a3 : %08X\n'
                  'a4 : %08X    a5 : %08X    a6 : %08X    a7 : %08X\n'
                  's0 : %08X    s1 : %08X    s2 : %08X    s3 : %08X\n'
                  's4 : %08X    s5 : %08X    s6 : %08X    s7 : %08X\n'
                  's8 : %08X    s9 : %08X    s10: %08X    s11: %08X\n'
                %(vals['pc'],   vals['ra'],  vals['sp'],
                  vals['gp'],   vals['tp'],  vals['fp'],
                  vals['t0'],   vals['t1'],  vals['t2'],
                  vals['t3'],   vals['t4'],  vals['t5'],  vals['t6'],
                  vals['a0'],   vals['a1'],  vals['a2'],  vals['a3'],
                  vals['a4'],   vals['a5'],  vals['a6'],  vals['a7'],
                  vals['s0'],   vals['s1'],  vals['s2'],  vals['s3'],
                  vals['s4'],   vals['s5'],  vals['s6'],  vals['s7'],
                  vals['s8'],   vals['s9'],  vals['s10'], vals['s11'],
                 ))
    
    @connection_required
    def do_reg(self, reg):
        '''Read core register. Syntax: reg <RegName>
Can only exec when Core halted\n'''
        if not self.xlk.halted():
            print('should halt first!\n')
            return

        val = self.xlk.read_reg(reg)

        print(f'\n0x{val:08X}\n')

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
set elf file path, Syntax: path elf <elfpath>\n'''
        if subcmd == None:
            maxlen = max(len(self.dllpath), len(self.svdpath), len(self.elfpath))
            print(f'{"√" if os.path.isfile(self.dllpath) else "×"}  {self.dllpath:{maxlen}}')
            print(f'{"√" if os.path.isfile(self.svdpath) else "×"}  {self.svdpath:{maxlen}}')
            print(f'{"√" if os.path.isfile(self.elfpath) else "×"}  {self.elfpath:{maxlen}}\n')

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

                        self.svdev = svd.SVD(self.svdpath).device

                    elif subcmd == 'elf':
                        self.elfpath = path

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
            elif pre_args[0] == 'elf': extra_paths = self.elfpaths
            else: return
            
            yield from ptkcmd.complete_path(' '.join([*pre_args[1:], curr_arg]), extra_paths, self.env)

    @connection_required
    def do_sv(self, input, val=None):
        '''svd-based peripheral register read and write
register read:        sv <peripheral>.<register>
register write:       sv <peripheral>.<register> <hex>
register field write: sv <peripheral>.<register>.<field> <dec>\n'''
        obj = self.svdev
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
            obj = self.svdev
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
        '''display CallStack information coming from elf file.\n'''
        if os.path.isfile(self.elfpath):
            cs = callstack.CallStack(self.elfpath)
            if cs.Functions:
                print(f'{cs}\n')

            else:
                print("elf file parse Fail\n")

        else:
            print("elf file Not Exists\n")

    def do_env(self):
        '''display enviriment variables\n'''
        for key, val in self.env.items():
            print(f'{key:<10s}{val}')
        print()

    def do_exit(self):
        self.xlk.close()
        sys.exit()

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
        self.conf.set('link',  'mode', self.mode)
        self.conf.set('link',  'speed', f'{self.speed} MHz')
        self.conf.set('paths', 'dllpath', self.dllpath)
        self.conf.set('paths', 'svdpath', repr(list(dict.fromkeys([self.svdpath] + self.svdpaths))))    # 保留顺序去重
        self.conf.set('paths', 'elfpath', repr(list(dict.fromkeys([self.elfpath] + self.elfpaths))))

        self.conf.write(open('setting.ini', 'w', encoding='utf-8'))


#with ipdb.launch_ipdb_on_exception():
if __name__ == '__main__':
    cmd = DAPCmdr()
    cmd.cmdloop()
