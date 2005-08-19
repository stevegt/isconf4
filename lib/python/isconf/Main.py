
import copy
import inspect
import os
import sys

from isconf.Config import Config
from isconf.Globals import *
from isconf.GPG import GPG
from isconf.Server import Server
from isconf.Socket import UNIXClientSocket

class Main:

    verbs = (
            'ci',     
            'exec',   
            'fork',    
            'snap',
            'start',
            'stop',
            'up',
    )

    def config(self,fname):
        if self.kwopt['verbose']:
            os.environ['VERBOSE'] = '1'
        os.environ.setdefault('VARISCONF',"/var/isconf")
        os.environ.setdefault('ISCONF_PORT',"65027")
        os.environ.setdefault('ISCONF_HTTP_PORT',"65028")
        hostname = os.popen('hostname','r').read().strip()
        os.environ.setdefault('HOSTNAME',hostname)
        hostname = os.environ['HOSTNAME']
        
        conf = Config(fname)
        vars = conf.match(hostname)
        self.info("adding to environment: %s" % str(vars))

        for (var,val) in vars.items():
            os.environ[var]=val

        # self.info(os.system("env"))

    def info(self,*msg):
        if not self.kwopt['verbose']:
            return
        self.error(*msg)

    def error(self,*msg):
        for m in msg:
            print >>sys.stderr, m
        print >>sys.stderr, "\n"

    def panic(self,*msg):
        self.error(*msg)
        sys.exit(99)


    def main(self):

        synopsis = """
        isconf [-hv] [-c config ] [-m message] {verb} ...
        
        """
        opt = {
            'c': ('config', '/etc/is.conf', "ISFS/ISconf configuration file" ),
            'h': ('help',    False, "this text" ),
            'm': ('message', None,  "changelog and branch lock message" ),
            'v': ('verbose', False, "show verbose output"),
        }
        ps = "\nVerb is one of: %s\n" % ', '.join(self.verbs)
        (kwopt,args,usage) = getkwopt(sys.argv[1:],opt)
        self.helptxt = synopsis + usage + ps
        if kwopt['help']: self.usage()
        self.kwopt = copy.deepcopy(kwopt)
        self.config(kwopt['config'])
        if not args: 
            self.usage("missing verb")
        self.args = copy.deepcopy(args)
        verb = args.pop(0)
        if not verb in self.verbs:
            self.usage("unknown verb")
        if verb in ('start','stop'):
            func = getattr(self,verb)
            rc = func(args)
            sys.exit(rc)
        client()

    def client(self):
        transport = UNIXClientSocket(varisconf = os.environ['VARISCONF'])
        isconf = ISconf4()
        rc = isconf.client(transport=transport,argv=self.args)
        sys.exit(rc)
        
    def start(self,argv):
        # detach from parent per Stevens
        # XXX need to allow for optional foreground operation
        if os.fork(): return 0
        os.chdir('/')
        os.setsid()
        os.umask(0)
        if os.fork(): sys.exit(0)
        # start daemon
        server = Server()
        rc = server.start()
        sys.exit(rc)

    def stop(self,argv):
        server = Server()
        rc = server.stop()
        sys.exit(rc)

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

if __name__ == "__main__":
    main = Main()
    main.main()

