import os
import re
import sys
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.styles import Style


class PtkCmd():
    prompt = '(PtkCmd) '
    intro = ''
    style = Style.from_dict({
        'prompt': '#6600ff',
    })
    help_header = '''Documented commands (type help <topic>):
=====================================================================\n'''

    def __init__(self, stdin=sys.stdin, stdout=sys.stdout, **psession_kwargs):
        self.stdin = stdin
        self.stdout = stdout

        psession_kwargs['completer'] = PtkCmdCompleter(self)
        psession_kwargs['style'] = self.style

        self.psession = PromptSession(**psession_kwargs)

        self.funs_do = {}
        self.funs_help = {}
        self.funs_complete = {}
        for name in dir(self.__class__):
            if name.startswith('do_'):
                self.funs_do[name[3:]] = getattr(self, name)
            elif name.startswith('help_'):
                self.funs_help[name[5:]] = getattr(self, name)
            elif name.startswith('complete_'):
                self.funs_complete[name[9:]] = getattr(self, name)

        self.cmds_do = sorted(self.funs_do.keys())

    def cmdloop(self):
        self.stdout.write(f'{self.intro}\n')
        self.preloop()
        while True:
            try:
                line = self.psession.prompt(self.prompt)
                if line is None:
                    break
            except EOFError:
                break

            line = self.precmd(line)
            line = self.onecmd(line)
            self.postcmd(line)
        self.postloop()

    def preloop(self):
        pass

    def precmd(self, line):
        return line.strip()

    def onecmd(self, line):
        if line == '':
            self.emptyline()
            return

        cmd_args = line.split()
        cmd,args = cmd_args[0], cmd_args[1:] if len(cmd_args) > 1 else []
        if cmd in self.funs_do:
            return self.funs_do[cmd](*args)
        else:
            return self.defaultdo(cmd, line)

    def emptyline(self):
        '''Called when an empty line is entered in response to the prompt. '''
        pass

    def defaultdo(self, cmd, line):
        '''Called when command not found. '''
        if cmd.endswith('?'):
            return self.onecmd(f'help {cmd[:-1]}')

        self.stdout.write(f'*** Unknown Command: {cmd}\n\n')

    def postcmd(self, line):
        pass

    def postloop(self):
        pass

    def do_help(self, *args):
        if len(args) == 0:
            self.stdout.write(self.help_header)
            self.columnize(self.cmds_do)
            self.stdout.write("\n")

        else:
            cmd = args[0]
            if cmd in self.funs_help:
                self.funs_help[cmd]()
            elif cmd in self.funs_do:
                if self.funs_do[cmd].__doc__:
                    self.stdout.write(f'{self.funs_do[cmd].__doc__}\n')
                else:
                    self.stdout.write(f'*** No doc for {cmd}\n\n')
            else:
                self.stdout.write(f'*** Unknown Command: {cmd}\n\n')

    def columnize(self, slist, displaywidth=80):
        import cmd
        cmd.Cmd.columnize(self, slist, displaywidth)


class PtkCmdCompleter(Completer):
    def __init__(self, ptkcmd):
        self.ptkcmd = ptkcmd

    def get_completions(self, document, complete_event):
        cmd_args = document.current_line_before_cursor.split()
        if len(cmd_args) == 1:
            cmd = cmd_args[0]
            if document.char_before_cursor != ' ':
                yield from [Completion(name, -len(cmd)) for name in self.ptkcmd.cmds_do if name.startswith(cmd)]

        elif len(cmd_args) > 1:
            cmd, args = cmd_args[0], cmd_args[1:]
            if document.char_before_cursor != ' ' and cmd in self.ptkcmd.funs_complete:
                yield from self.ptkcmd.funs_complete[cmd](args[:-1], args[-1], document, complete_event)


def complete_path(input, extra_paths=[], env={}):
    match = re.match(r'%\w+%', input)
    if match:
        input = input.replace(match.group(0), env[match.group(0)])

    if re.match(r'[a-zA-Z]:$', input):   # 输入"D:"时不补全，输入"D:\"或"D:/"时才开始补全
        return

    if input.count('/') or input.count('\\'):
        dirname, basename = os.path.split(input)

    else:
        dirname, basename = os.getcwd(), input

    if os.path.isdir(dirname): # return True if path is an existing directory
        paths = [path for path in fuzzy_match(input, extra_paths)]
        items = [item for item in fuzzy_match(basename, [item for item in os.listdir(dirname) if not item.startswith('$')])]
        
        yield from [*[Completion(path, -len(input)) for path in paths], *[Completion(item, -len(basename)) for item in items]]


def fuzzy_match(input, slist, sort=True):
    matched = []
    pattern = '.*?'.join(map(re.escape, input))
    pattern = '(?=({0}))'.format(pattern)   # lookahead regex to manage overlapping matches
    regex = re.compile(pattern, re.IGNORECASE)
    for item in slist:
        r = list(regex.finditer(item))
        if r:
            best = min(r, key=lambda x: len(x.group(1)))   # find shortest match
            matched.append((len(best.group(1)), best.start(), item))

    if sort: matched.sort()

    return (z[-1] for z in matched)
