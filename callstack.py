#!python3
import os
import re
import collections


Function = collections.namedtuple('Function','start end callees callers')   # callees: 此函数调用的函数
                                                                            #   address1 callee1，此函数在address1处调用了callee1
                                                                            # callers: 调用此函数的函数
                                                                            #   caller1 address1，caller1在address1处调用了此函数


class CallStack():
    def __init__(self, path):
        text = open(path, 'r', encoding='utf-8', errors='ignore').read()

        self.Functions = collections.OrderedDict()

        self.parseDis_MDK(text)
        if not self.Functions:
            self.parseDis_GCC(text)
            if not self.Functions:
                self.parseDis_IAR(text)
                if not self.Functions:
                    return              # disassembler parse fail

        for name in self.Functions:
            for name2, func in self.Functions.items():
                for addr, callee in func.callees:                           # name2调用的函数中有name
                    if name == callee:
                        self.Functions[name].callers.append((name2, addr))  # name的调用者中添加name2
                        # TODO: 如果name2中多处调用name，怎么处理
                        #break

    def parseDis_MDK(self, text):
        for match in re.finditer(r'\n    ([A-Za-z_][A-Za-z_0-9]*)\n(        (0x[0-9a-f]{8}):[\s\S]+?)(?=\n    [A-Za-z_\$])', text):
            name, start, end = match.group(1), int(match.group(3), 16), int(match.group(3), 16)

            lastline = match.group(2).strip().split('\n')[-1]
            match2 = re.match(r'        (0x[0-9a-f]{8}):', lastline)
            if match2:
                end = int(match2.group(1), 16)

            self.Functions[name] = Function(start, end, [], [])

            for line in match.group(2).split('\n'):
                match2 = re.match(r'        (0x[0-9a-f]{8}):\s+[0-9a-f]{4,8}\s+\S+\s+B[L.W]*\s+([A-Za-z_][A-Za-z0-9_]*) ;', line)
                if match2:
                    address, callee = int(match2.group(1), 16), match2.group(2)
                    self.Functions[name].callees.append((address, callee))

    def parseDis_IAR(self, text):
        for match in re.finditer(r"\n\s+([A-Za-z_][A-Za-z0-9_]+):\n(\s+(0x[0-9a-f']+): 0x[0-9a-f]{4}[\s\S]+?)\n\s+((// [}a-z])|(\$)|(`.text))", text):
            name, start, end = match.group(1), int(match.group(3).replace("'", ''), 16), int(match.group(3).replace("'", ''), 16)

            lastline = match.group(2).strip().split('\n')[-1]
            match2 = re.match(r"\s+(0x[0-9a-f']+): 0x[0-9a-f]{4}", lastline)
            if match2:
                end = int(match2.group(1).replace("'", ''), 16)

            self.Functions[name] = Function(start, end, [], [])

            for line in match.group(2).split('\n'):
                match2 = re.match(r"\s+(0x[0-9a-f']+): 0x[0-9a-f]{4} 0x[0-9a-f]{4}\s+BL\s+([A-Za-z_][A-Za-z0-9_]+)\s+; 0x[0-9a-f']+", line)
                if match2:
                    address, callee = int(match2.group(1).replace("'", ''), 16), match2.group(2)
                    self.Functions[name].callees.append((address, callee))

    def parseDis_GCC(self, text):
        for match in re.finditer(r'\n([0-9a-f]{8}) <([A-Za-z_][A-Za-z_0-9]*)>:([\s\S]+?)(?=\n\n)', text):
            name, start, end = match.group(2), int(match.group(1), 16), int(match.group(1), 16)

            lastline = match.group(3).strip().split('\n')[-1]
            match2 = re.match(r'\s+([0-9a-f]{1,8}):\s+[0-9a-f]{4}', lastline)
            if match2:
                end = int(match2.group(1), 16)

            self.Functions[name] = Function(start, end, [], [])

            for line in match.group(3).split('\n'):
                match2 = re.match(r'\s+([0-9a-f]{1,8}):.+?bl\s+[0-9a-f]+\s<([A-Za-z_][A-Za-z0-9_]*)>', line)
                if match2:
                    address, callee = int(match2.group(1), 16), match2.group(2)
                    self.Functions[name].callees.append((address, callee))

    def parseStack(self, stackMem):
        Program_Start = min([func.start for (name, func) in self.Functions.items()])
        Program_End   = max([func.end   for (name, func) in self.Functions.items()])

        callStack, index = [], 0
        while index < len(stackMem):
            if ((index <= len(stackMem) - 8) and
                (Program_Start <= stackMem[index+5] <= Program_End and stackMem[index+5]%2 == 1) and 
                (Program_Start <= stackMem[index+6] <= Program_End and stackMem[index+6]%2 == 0) and 
                ((stackMem[index+7] >> 24) & 1 == 1)):          # 中断服务

                for name, func in self.Functions.items():       # 找出中断压栈时正在执行的函数
                    if func.start <= stackMem[index+6] <= func.end:
                        callStack.append((stackMem[index+6], name))
                        break

                else:
                    return 'Cannot find the function be interrupted'

                index += 8

            elif index == 0:
                return 'Invalid Exception Stack Frame'

            else:                                               # 函数调用
                for name, addr in self.Functions[callStack[-1][1]].callers: # 遍历函数的调用者，谁在栈内
                    if stackMem[index] == addr + 4 + 1:   # 存入LR的值是函数调用指令地址 + 4，然后地址低位为1
                        callStack.append((stackMem[index], name))
                        break

                index += 1
        
        ss = 'Call Stack:\n'
        for addr, name in callStack:
            ss += f'0x{addr:08X}  {name}\n'

        return ss

    def __str__(self):
        ss = ''
        
        for name, func in self.Functions.items():
            ss += f'\n{name:30s} @ 0x{func.start:08X} - 0x{func.end:08X}\n'
            for addr, name in func.callees:
                ss += f'    0x{addr:08X} {name}\n'

        for name, func in self.Functions.items():
            ss += f'\n{name:30s} called by:\n'
            for name, addr in func.callers:
                ss += f'    {name:30s} @ 0x{addr:08X}\n'

        return ss


if __name__ == '__main__':
    cs = CallStack('docs/STM32F1.dis')
    print(cs)
