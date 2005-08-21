
import copy
import getopt
import inspect
import os
import sys
import time

import isconf
from isconf.Config import Config
from isconf.Globals import *
from isconf.GPG import GPG
from isconf.Server import Server
from isconf.Socket import UNIXClientSocket
from isconf.Kernel import kernel, Restart

class Main:

    verbs = (
            'ci',     
            'exec',   
            'fork',    
            'restart',
            'snap',
            'start',
            'stop',
            'up',
    )

    def config(self,fname):
        if self.kwopt['debug']:
            os.environ['DEBUG'] = '1'
            os.environ['VERBOSE'] = '1'
        if self.kwopt['verbose']:
            os.environ['VERBOSE'] = '1'
        os.environ.setdefault('VARISCONF',"/var/isconf")
        os.environ.setdefault('ISFS_HOME',"/var/isfs")
        os.environ.setdefault('ISFS_DOMAIN',"example.com")
        os.environ.setdefault('ISFS_PORT',"65027")
        os.environ.setdefault('ISFS_HTTP_PORT',"65028")
        hostname = os.popen('hostname','r').read().strip()
        os.environ.setdefault('HOSTNAME',hostname)
        hostname = os.environ['HOSTNAME']
        
        conf = Config(fname)
        vars = conf.match(hostname)
        debug("adding to environment: %s" % str(vars))

        for (var,val) in vars.items():
            os.environ[var]=val

        isfshome=os.environ['ISFS_HOME']
        os.environ.setdefault('ISFS_CACHE',"%s/cache" % isfshome)

        debug(os.popen("env").read())

    def main(self):
        synopsis = """
        isconf [-Dhv] [-c config ] [-m message] {verb} [verb args ...]
        
        """
        opt = {
            'c': ('config', '/etc/is.conf', "ISFS/ISconf configuration file" ),
            'D': ('debug',   False, "show debugging output"),
            'h': ('help',    False, "this text" ),
            'm': ('message', None,  "changelog and branch lock message" ),
            'v': ('verbose', False, "show verbose output"),
        }
        ps = "\nVerb is one of: %s\n" % ', '.join(self.verbs)
        ps += "\nVerb and verb args can be interleaved with other flags."
        self.cwd = os.getcwd()
        (kwopt,args,usage) = getkwopt(sys.argv[1:],opt)
        self.helptxt = synopsis + usage + ps
        if kwopt['help']: self.usage()
        if not args: 
            self.usage("missing verb")
        self.kwopt = copy.deepcopy(kwopt)
        self.config(kwopt['config'])
        self.args = copy.deepcopy(args)
        verb = args.pop(0)
        if not verb in self.verbs:
            self.usage("unknown verb")
        if verb in ('start','stop','restart'):
            func = getattr(self,verb)
            rc = func(args)
            sys.exit(rc)
        try:
            rc = self.client()
        except KeyboardInterrupt:
            sys.exit(2)
        sys.exit(rc)


    def client(self):
        ctl = "%s/.ctl" % os.environ['VARISCONF']
        transport = UNIXClientSocket(path = ctl)
        rc = isconf.ISconf.client(
                transport=transport,argv=self.args,kwopt=self.kwopt)
        return rc
        
    def restart(self,argv):
        try:
            self.stop(argv)
        except:
            pass
        time.sleep(1)
        self.start(argv)

    def start(self,argv):
        # detach from parent per Stevens
        # XXX need to allow for optional foreground operation
        if os.fork(): return 0
        os.chdir('/')
        os.setsid()
        os.umask(0)
        if os.fork(): sys.exit(0)
        # start daemon
        while True:
            try:
                server = Server()
                rc = server.start()
            except Restart:
                error("restarting [%s]..." % ' '.join(sys.argv))
                os.chdir(self.cwd)
                # close everything down
                kernel.killall()
                server = None 
                time.sleep(1)
                os.execvp(sys.argv[0],sys.argv)
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

    Get command line options and positional arguments.  Positional
    arguments can be interleaved with option flags.

    Returns help text if help=True 

    Returns (kwopt,args) otherwise.

    Sample input:

        opt = {
            'p': ('port', 9999, "port to listen on"),
            'v': ('verbose', False, "verbose"),
        }
        
    Sample kwopt return value (with empty command line):

        kwopt = {
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

    opts=[]
    args=[]
    dargv = argv[:]
    # extract flags interleaved with positional args
    while len(dargv):
        (o,dargv) = getopt.getopt(dargv, optstr, longopts)
        opts += o
        if len(dargv):
            args.append(dargv.pop(0))
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

