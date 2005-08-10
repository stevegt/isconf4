
import copy
import inspect
import os
import sys

from isconf.Globals import *
from isconf.GPG import GPG
from isconf.Server import Server
from isconf.Test import Test

class Main:
    """XXX explanation about use of doc strings for help text"""

    verbs = (
            'ci',     
            'exec',   
            'fork',    
            'snap',
            'server',
            'up',
    )

    def XXX_getconfig(self):
        # parse config
        defaults={}
        defaults['var'] = "/var/isconf/current"
        defaults['cache'] = defaults['var'] + "/cache"
        hostname = os.uname()[1]
        conf = ConfigParser.ConfigParser(defaults)
        # XXX i hate these names
        conf.read(home+".hosts.conf", "/var/isconf/hosts.conf", "/etc/hosts.conf")
        conf.read(home+".isconf.cf", "/var/isconf/isconf.cf", "/etc/isconf.cf")
        # XXX see lab/config

    def _config(self):
        if self.kwopt['verbose']:
            os.environ['VERBOSE'] = '1'
        os.environ['VARISCONF'] = "/tmp/var/isconf" # XXX
        os.environ['ISCONF_PORT'] = str(self.kwopt['port'])
        

    def main(self):

        synopsis = """
        isconf [-hv] [-c config ] [-m message] [-p port] {verb} ...
        
        """
        global verbose
        opt = {
            'c': ('config', '/etc/is.conf', "ISFS/ISconf configuration file" ),
            'h': ('help',    False, "this text" ),
            'm': ('message', None,  "changelog and branch lock message" ),
            'p': ('port',    9999,  "TCP/UDP port for interhost comms" ),
            'v': ('verbose', False, "show verbose output"),
        }
        ps = "\nVerb is one of: %s\n" % ', '.join(self.verbs)
        (kwopt,args,usage) = getkwopt(sys.argv[1:],opt)
        self.helptxt = synopsis + usage + ps
        if kwopt['help']: self.usage()
        self.kwopt = copy.deepcopy(kwopt)
        self._config()
        if not args: 
            self.usage("missing verb")
        self.args = copy.deepcopy(args)
        verb = args.pop(0)
        if not verb in self.verbs:
            self.usage("unknown verb")
        if verb in ('help', 'server'):
            self.verb = verb
            func = getattr(self,verb)
            rc = func(args)
            sys.exit(rc)
        transport = UNIXClientSocket(varisconf = os.environ['VARISCONF'])
        isconf = ISconf4(transport=transport)
        rc = isconf.client(self.args)
        sys.exit(rc)
        
    def server(self,argv):
        # detach from parent per Stevens
        os.fork() and sys.exit(0)
        os.chdir('/')
        os.setsid()
        os.umask(0)
        os.fork() and sys.exit(0)
        # start
        server = Server()
        server.serve()
        sys.exit(0)

    def usage(self,msg=None):
        # avoid passing obj -- use:
        # inspect.stack()[1][0].f_code.co_consts[0] to get docstring
        # doc = inspect.stack()[1][0].f_code.co_consts[0]
        if not msg: msg = ""
        usagetxt = "%s\nusage: %s\n\n" % (
            msg,
            self.helptxt.strip()
        )
        print >>sys.stderr, usagetxt
        sys.exit(1)

def getkwopt(argv,opt={}): 
    """
    Get command line options and positional arguments.

    Returns help text if help=True 

    Returns (kwopt,args) otherwise.

    Sample input:

        opt = {
            'd': ('varisconf', "/var/isconf", "base of cache"),
            'p': ('port', 9999, "port to listen on"),
            'v': ('verbose', False, "verbose"),
        }
        
    Sample kwopt return value (with empty command line):

        kwopt = {
            'varisconf': "/var/isconf",
            'port': 9999,
            'verbose': False,
        }
    """
    kwopt = {}
    optstr = ''
    longopts = []
    if opt:
        usagetxt = "options:\n"
    else:
        usagetxt = ""
    for short in opt.keys():
        long    = opt[short][0]
        default = opt[short][1]
        desc    = opt[short][2]
        kwopt[long] = default
        optstr += short
        longopt = long
        opthelp = "  -%s, --%s" % (short,long)
        if default is not True and default is not False:
            optstr += ':'
            longopt += '='
            opthelp += '=' + str(default)
        longopts.append(longopt)
        sep=""
        if len(opthelp) > 20: 
            sep="\n" + " " * 22
        usagetxt += "%-22s%s%s\n" % (opthelp,sep,desc)
    (opts, args) = getopt.getopt(argv, optstr, longopts)
    for (flag,value) in opts:
        if value == '': 
            value = True
        long = None
        if flag.startswith('--'): 
            long = flag[2:]
        else:
            short = flag[1:] 
            long = opt[short][0]
        assert long
        kwopt[long] = value
    return (kwopt,args,usagetxt)

