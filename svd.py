#! python3
import re
import collections
import xml.etree.ElementTree as ET


class Device():
    def __init__(self, name):
        self.name = name
        self.cpu  = Cpu()
        self.peripherals = {}

    @property
    def children(self):
        return self.peripherals

    def __str__(self):
        ss = f'{self.name} ({self.cpu.name})\n'

        for peri in self.peripherals.values():
            ss += str(peri)

        return ss


class Cpu():
    def __init__(self, name='Cortex-M0'):
        self.name = name


class Peripheral():
    def __init__(self, name, addr, nwrd):
        self.name = name
        self.addr = addr
        self.nwrd = nwrd
        self.registers = collections.OrderedDict()

    @property
    def children(self):
        return self.registers

    def load_value(self, addr_values):
        for obj in self.registers.values():
            obj.load_value(addr_values)

    def __str__(self):
        ss = f'\n{self.name:<7s} @ {self.addr:08X}\n'

        for obj in self.registers.values():  # register or cluster
            ss += str(obj)

        return ss


class Register():
    def __init__(self, name, addr, desc):
        self.name = name
        self.addr = addr
        self.desc = desc
        self.value = 0x0
        self.fields = collections.OrderedDict()

    @property
    def children(self):
        return self.fields

    def load_value(self, addr_values):
        self.value = addr_values[self.addr]

    def __str__(self):
        ss = f'    {self.addr:06X}  {self.name:<12s} {self.value:08X}\n'

        for field in self.fields.values():
            ss += str(field)

        return ss


class RegisterArray():
    def __init__(self, name, addr, reglist):
        self.name = name
        self.addr = addr
        self.reglist = reglist
    
    def __getitem__(self, index):
        return self.reglist[index]

    def __len__(self):
        return len(self.reglist)

    def load_value(self, addr_values):
        for reg in self.reglist:
            reg.load_value(addr_values)

    def __str__(self):
        ss = f'    {self.addr:06X}  {self.name}[{len(self)}]'

        for i, reg in enumerate(self):
            if i % 4 == 0:
                ss += f'\n    {self.addr+i*4:06X} '

            ss += f' {reg.value:08X}'

        return f'{ss}\n'


class Cluster():
    def __init__(self, name, addr, nwrd):
        self.name = name
        self.addr = addr
        self.nwrd = nwrd
        self.registers = collections.OrderedDict()

    @property
    def children(self):
        return self.registers

    def load_value(self, addr_values):
        for reg in self.registers.values():
            reg.load_value(addr_values)

    def __str__(self):
        ss = f'  {self.addr:06X}  {self.name}\n'

        for reg in self.registers.values():
            ss += str(reg)

        return ss


class Field():
    def __init__(self, name, pos, mask, desc, reg):
        self.name = name
        self.pos  = pos
        self.mask = mask
        self.desc = desc
        self.reg  = reg   # register the field belong to
    
    @property
    def addr(self):
        return self.reg.addr
    
    @property
    def value(self):
        return (self.reg.value & self.mask) >> self.pos

    def load_value(self, addr_values):
        self.reg.load_value(addr_values)

    def __str__(self):
        return f'        {self.pos:>2d}  {self.name:<12s} {self.value}\n'


class SVD():
    def __init__(self, file):
        self.xml = ET.parse(file).getroot()

        self.dev = Device(self.xml.find('./name').text)

        if self.xml.find('./cpu'):
            self.dev.cpu.name = re.sub(r'CM(\d+)', r'Cortex-M\1', self.xml.find('./cpu/name').text)

        for peripheral in self.xml.iterfind('./peripherals/peripheral'):
            name = peripheral.find('./name').text
            addr = peripheral.find('./baseAddress').text

            if 'derivedFrom' in peripheral.attrib:
                peripheral = self.get_peripheral_by_name(peripheral.attrib['derivedFrom'])

            size = peripheral.find('./addressBlock/size').text

            peri = Peripheral(name, int(addr, 16), int(size, 16)//4)
            self.dev.peripherals[name] = peri

            for reg_or_clus in peripheral.find('./registers').iterfind('./*'):
                if reg_or_clus.tag == 'register':
                    self.add_register(peri, reg_or_clus)
                
                elif reg_or_clus.tag == 'cluster':
                    name = reg_or_clus.find('./name').text
                    addr = reg_or_clus.find('./addressOffset').text

                    clus = Cluster(name, int(addr, 16), 0)
                    peri.registers[name] = clus

                    for register in reg_or_clus.iterfind('./register'):
                        self.add_register(clus, register)

                    last_reg = next(reversed(clus.registers.values()))
                    if isinstance(last_reg, RegisterArray): last_reg = last_reg[-1]
                    clus.nwrd = ((last_reg.addr + 4) - clus.addr) // 4

                else:
                    raise Exception('error element under peripheral/registers')

    @property
    def device(self):
        return self.dev
    
    def get_peripheral_by_name(self, name):
        for peripheral in self.xml.iterfind('./peripherals/peripheral'):
            if peripheral.find('./name').text == name:
                return peripheral

    def add_register(self, peri_or_clus, register):
        name = register.find('./name').text
        addr = register.find('./addressOffset').text
        desc = register.find('./description').text if register.find('./description') else ''

        if register.find('./dim') != None:
            name = name[:name.index('[')]
            nwrd = register.find('./dim').text
            nwrd = int(nwrd)
        else:
            nwrd = 1

        addr = int(addr, 16)
        if isinstance(peri_or_clus, Cluster):
            addr += peri_or_clus.addr

        if nwrd == 1:
            peri_or_clus.registers[name] = self.new_register(name, addr, desc, register)
        else:
            peri_or_clus.registers[name] = RegisterArray(name, addr, [self.new_register(name, addr+i*4, desc, register) for i in range(nwrd)])

    def new_register(self, name, addr, desc, register):
        regi = Register(name, addr, desc)

        for field in register.iterfind('./fields/field'):
            self.add_field(regi, field)

        return regi

    def add_field(self, regi, field):
        name = field.find('./name').text
        pos  = field.find('./bitOffset').text
        nbit = field.find('./bitWidth').text
        desc = field.find('./description').text if field.find('./description') else ''

        mask = ((1 << int(nbit)) - 1) << int(pos)
        regi.fields[name] = Field(name, int(pos), mask, desc, regi)


if __name__ == '__main__':
    dev = SVD('docs/STM32F103xx.svd').device
    print(dev)
