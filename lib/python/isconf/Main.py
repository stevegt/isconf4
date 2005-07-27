
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
            'date',
            'doctest',
            'exec',
            'fork',
            'help',
            'snap',
            'selftest',
            'server',
            'up',
        )

    def _getconfig(self):
        # parse config
        defaults={}
        defaults['var'] = "/var/isconf/current"
        defaults['cache'] = defaults['var'] + "/cache"
        hostname = os.uname()[1]
        conf = ConfigParser.ConfigParser(defaults)
        # XXX i hate these names
        conf.read(home+".hosts.conf", "/var/isconf/hosts.conf", "/etc/hosts.conf")
        conf.read(home+".isconf.cf", "/var/isconf/isconf.cf", "/etc/isconf.cf")

        # XXX 
        # print conf.sections()
        # print conf.get('DEFAULT','var')

    def main(self):

        """[-hv] [-m message] {verb} [verb_options] ..."""
        global verbose
        opt={
            'd': ('varisconf', '/var/isconf', "ISFS/ISconf data directory (relative to rootdir)" ),
            'h': ('help',    False, "this text" ),
            'm': ('message', None,  "changelog and branch lock message" ),
            'r': ('rootdir',    '/',   "root directory (target of modifications)" ),
            'v': ('verbose', False, "show debug output"),
        }
        ps = "verb is one of: %s\n" % ', '.join(self.verbs)
        def usage(msg=None): self.usage(self.main,opt,msg,ps)

        # self.home = os.getenv("HOME")
        
        (kwopt,args) = getkwopt(sys.argv[1:],opt)
        if kwopt['help']: usage()
        kwopt['varisconf'] = "%s/%s" % (
            kwopt['rootdir'].rstrip('/'), kwopt['varisconf'].lstrip('/'),
        )
        self.kwopt = copy.deepcopy(kwopt)
        verbose = kwopt['verbose']
        if not args: 
            usage("missing verb")
        self.args = copy.deepcopy(args)
        verb = args.pop(0)
        if not verb in self.verbs:
            usage("unknown verb")
        if verb in ('doctest', 'selftest', 'help', 'server'):
            self.verb = verb
            func = getattr(self,verb)
            rc = func(args)
            sys.exit(rc)
        transport = UNIXClientSocket(varisconf = kwopt['varisconf'])
        isconf = ISconf4(transport=transport)
        rc = isconf.client(self.args)
        sys.exit(rc)
        
    def help(self,argv):
        """isconf help {verb}"""
        raise
        opt={}
        ps = "verb is one of: %s\n" % ', '.join(self.verbs)
        def usage(msg=None): self.usage(self.help,opt,msg,ps)
        verb = argv[0]
        if not verb in self.verbs:
            usage("unknown verb")
        func = getattr(self,verb)
        func(('-h'))
        return 0

    def doctest(self,argv):
        """isconf doctest"""
        opt={
            'h': ('help',       False, "this text" ),
        }
        ps = "run docstring self-tests"
        def usage(msg=None): self.usage(self.selftest,opt,msg,ps)
        (kwopt,args) = getkwopt(argv,opt)
        if kwopt['help']: usage()

        test = Test()
        return test.doctest()

    def server(self,argv):
        """isconf server"""
        opt={
            'h': ('help',       False, "this text" ),
            'p': ('port',       9999,  "TCP port to listen on" ),
        }
        ps = "start isconf server daemon"
        def usage(msg=None): self.usage(self.server,opt,msg,ps)
        (kwopt,args) = getkwopt(argv,opt)
        if kwopt['help']: usage()
        # detach from parent per Stevens
        os.fork() and sys.exit(0)
        os.chdir('/')
        os.setsid()
        os.umask(0)
        os.fork() and sys.exit(0)
        # start
        server = Server(
            varisconf = self.kwopt['varisconf'],
            port = int(kwopt['port']),
            )
        server.serve()
        sys.exit(0)

    def selftest(self,argv):
        """isconf selftest [-p]"""
        opt={
            'd': ('dirty',      False, "don't clean up -- leave /tmp dirty" ),
            'h': ('help',       False, "this text" ),
            'p': ('persistent', False, "leave a test server daemon running" ),
        }
        ps = "run standalone self-tests"
        def usage(msg=None): self.usage(self.selftest,opt,msg,ps)
        (kwopt,args) = getkwopt(argv,opt)
        if kwopt['help']: usage()

        test = Test()
        return test.selftest(**kwopt)

    def usage(self,obj,opt=None,msg=None,ps="\n"):
        # XXX avoid passing obj -- use:
        # inspect.stack()[1][0].f_code.co_consts[0] to get docstring
        doc = inspect.getdoc(obj)
        if not msg: msg = ""
        usagetxt = "%s\nusage: %s %s\n\n%s\n%s" % (
            msg,
            sys.argv[0], 
            doc,
            getkwopt(None,opt,help=True),
            ps
        )
        print >>sys.stderr, usagetxt
        sys.exit(1)

