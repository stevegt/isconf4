
import os
import re
import sys

class Config:

    def __init__(self,fname):
        self.fname = fname
        self.section = {}
        self.sections = []
        (START,SECTION) = range(2)
        state=START
        name=''
        self.i=0
        config = open(fname,'r')
        for line in config:
            self.i += 1
            # skip comments
            if re.match('\s*#', line):
                continue
            if re.match('^\s*$', line):
                state=START
                name=''
                includes=[]
                continue
            m = re.match('(\S+.*):\s*(.*)',line)
            if m:
                # name: inc1 inc2
                state=SECTION
                names = m.group(1).strip().split()
                includes = ['DEFAULT'] + m.group(2).split()
                for name in names:
                    self.sections.append(name)
                    self.section.setdefault(name,{})
                    for inc in includes:
                        if not self.section.has_key(inc):
                            self.error("section not found: %s" % inc)
                        for (var,val) in self.section[inc].items():
                            self.section[name][var]=val
                continue
            if state is SECTION:
                m = re.match('^\s+(\w+)\s*=\s*(.*)', line)
                if not m:
                    self.error("syntax error")
                var = m.group(1).strip()
                val = m.group(2).strip()
                self.section[name][var]=val
                continue
            self.error("unknown input, state %s: %s" % (state,line))

    # XXX convert to global error
    def error(self,msg):
        raise ConfigurationError("%s line %d: %s" % (self.fname,self.i,msg))

    def match(self,hostname):
        vars={}
        for name in self.sections:
            if name == 'DEFAULT':
                vars.update(self.section[name])
            if name == hostname:
                vars.update(self.section[name])
                break
            if name.startswith('^') and re.match(name,hostname):
                # print >>sys.stderr, "config matched %s" % name
                vars.update(self.section[name])
                break
        return vars

class ConfigurationError(Exception): pass
