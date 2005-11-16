
import copy
import getopt
import inspect
import os
import signal
import sys
import time

try:
    import profile
except:
    pass

import isconf
from isconf.Config import Config
from isconf.Errno import iserrno
from isconf.Globals import *
from isconf.GPG import GPG
from isconf.Server import Server
from isconf.Socket import UNIXClientSocket
from isconf.Kernel import kernel, Restart

class Main:

    verbs = (
            'lock',
            'unlock',
            'snap',
            'exec',   
            'reboot',   
            'ci',     
            'up',
            'fork',    
            'migrate',    
            'start',
            'stop',
            'restart',
    )

    def config(self,fname):
        if not self.kwopt['quiet']:
            os.environ['VERBOSE'] = '1'
        if self.kwopt['debug']:
            os.environ['DEBUG'] = '1'
            os.environ['VERBOSE'] = '1'
        # if self.kwopt['reboot_ok']:
        #     os.environ['IS_REBOOT_OK'] = '1'
        os.environ.setdefault('LOGNAME',"root")
        os.environ.setdefault('IS_HOME',"/var/is")
        # os.environ.setdefault('IS_DOMAIN',"localdomain")
        os.environ.setdefault('IS_PORT',"65027")
        os.environ.setdefault('IS_HTTP_PORT',"65028")
        hostname = os.popen('hostname','r').read().strip()
        os.environ.setdefault('HOSTNAME',hostname)
        hostname = os.environ['HOSTNAME']
        
        if os.path.exists(fname):
            conf = Config(fname)
            vars = conf.match(hostname)
            debug("adding to environment: %s" % str(vars))
            for (var,val) in vars.items():
                os.environ[var]=val
        else:
            debug("%s not found -- using defaults" % fname)

        domfn = os.path.join(os.environ['IS_HOME'],"conf/domain")
        if os.path.exists(domfn):
            os.environ['IS_DOMAIN'] = open(domfn,'r').read().strip()
        elif not os.environ.has_key('IS_DOMAIN'):
            error("%s is missing -- see install instructions" % domfn)
        

        debug(os.popen("env").read())

    def main(self):
        synopsis = """
        isconf [-DhrqV] [-c config ] [-m message] {verb} [verb args ...]
        \n"""
        opt = {
            'c': ('config', '/etc/is/main.cf', "top-level configuration file" ),
            'D': ('debug',   False, "show debugging output"),
            'h': ('help',    False, "this text" ),
            'm': ('message', None,  "changelog and branch lock message" ),
            'r': ('reboot_ok',False,"reboot during update if needed" ),
            'q': ('quiet',   False, "don't show verbose output"),
            'V': ('version', False, "show version"),
        }
        ps = "\nVerb is one of: %s\n" % ', '.join(self.verbs)
        # ps += "\nVerb and verb args can be interleaved with other flags."
        self.cwd = os.getcwd()
        (kwopt,args,usage) = getkwopt(sys.argv[1:],opt)
        self.helptxt = synopsis + usage + ps
        if kwopt['help']: self.usage()
        if kwopt['version']:
            from isconf.version import release
            print release()
            sys.exit(0)
        if not args: 
            self.usage("missing verb")
        self.kwopt = copy.deepcopy(kwopt)
        self.config(kwopt['config'])
        self.args = copy.deepcopy(args)
        verb = args.pop(0)
        if not verb in self.verbs:
            self.usage("unknown verb")
        if verb == 'version':
            from isconf.version import release
            print release()
            sys.exit(0)
        if verb in ('start','stop','restart'):
        # if verb in ('start','restart'):
            func = getattr(self,verb)
            rc = func(args)
            sys.exit(rc)
        try:
            rc = self.client()
        except KeyboardInterrupt:
            sys.exit(2)
        sys.exit(rc)


    def client(self):
        ctl = "%s/conf/.ctl" % os.environ['IS_HOME']
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
        home = os.environ['IS_HOME']
        if not os.path.isdir(home):
            os.makedirs(home,0700)
        # os.chdir(home)
        if not os.environ.has_key('NOFORK'):
            # XXX don't return until server responds to ping msg
            if os.fork(): return 0
            os.chdir(home)
            os.setsid()
            os.umask(0) # XXX
            signal.signal(signal.SIGHUP,signal.SIG_IGN)
            if os.fork(): sys.exit(0)
            # XXX syslog
            si = open("/dev/null", 'r')
            so = open("/tmp/isconf.stdout", 'w', 0)
            se = open("/tmp/isconf.stderr", 'w', 0)
            os.dup2(si.fileno(), sys.stdin.fileno())
            os.dup2(so.fileno(), sys.stdout.fileno())
            os.dup2(se.fileno(), sys.stderr.fileno())
        # start daemon
        try:
            server = Server()
            rc = server.start()
            sys.exit(rc)
        except Restart:
            warn("daemon exiting")
            sys.exit(1)
            # XXX
            warn("restarting: `%s`..." % ' '.join(sys.argv))
            os.chdir(self.cwd)
            # close everything down
            kernel.killall()
            server = None 
            time.sleep(1)
            os.execvp(sys.argv[0],sys.argv)
        except SystemExit, e:
            sys.exit(e)
        sys.exit(0)

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
        sys.exit(iserrno.EINVAL)

def getkwopt(argv,opt={},interleave=False): 
    """

    Get command line options and positional arguments.  Positional
    arguments can be interleaved with option flags if interleave=True.

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
    if interleave:
        # extract flags interleaved with positional args
        while len(dargv):
            (o,dargv) = getopt.getopt(dargv, optstr, longopts)
            opts += o
            if len(dargv):
                args.append(dargv.pop(0))
    else:
        (opts,args) = getopt.getopt(dargv, optstr, longopts)
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

