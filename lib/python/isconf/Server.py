# vim:set expandtab:
# vim:set foldmethod=indent:
# vim:set shiftwidth=4:
# vim:set tabstop=4:

from __future__ import generators
import errno
import os
import re
import select
import socket
import sys
import time
import isconf
from isconf.Globals import *
from isconf.GPG import GPG
from isconf.ISdlink1 import ISdlink1
import isconf.ISFS1
from isconf.Kernel import kernel, Event
import rpc822

print "svr", kernel

class EchoTest:

    def __init__(self,transport):
        self.transport=transport

    def run(self,*args,**kwargs):
        kernel.info("starting EchoTest.run")
        rxd = ''
        while True:
            yield None
            # rxd = self.transport.read(1)
            # self.transport.write(rxd)
            rxd += self.transport.read(1)
            if '\n' in rxd: 
                self.transport.write(rxd)
                rxd = ''
        return 


class Peer:
    # XXX deprecate in favor of per-class routing tables:
    # 
    # have            get
    #
    # pathname        ISFS instance    
    # Message-Id      ISdmesh1 instance
    # Fingerprint     ISdlink1 instance
    # IP              ServerSocket instance
   
    
    def __init__(self, role='client'):
        self.layers = []
        self.role = role
        self.fingerprint = None

    def addLayer(self,layer):
        self.layers.append(layer)

    def state(self):
        return self.layers[0].state

class Server:

    def __init__(self,**kwargs):
        self.varisconf = kwargs.get('varisconf',"/var/isconf")
        self.port = kwargs.get('port',9999)
        self.ctlpath = kwargs.get('ctlpath',"%s/.ctl" % self.varisconf)
        self.pidpath = kwargs.get('pidpath',"%s/.pid" % self.varisconf)
        if not os.path.isdir(self.varisconf):
            os.makedirs(self.varisconf,0700)
        open(self.pidpath,'w').write("%d\n" % os.getpid())

    def serve(self):
        """be a server forever"""
        self.gpgsetup()
        kernel.run(self.init)

    def init(self,*args,**kwargs):
        """parent of all tasks"""
        yield kernel.sigspawn, self.rpc822()
        unix = UNIXServerFactory(path=self.ctlpath)
        yield kernel.sigspawn, unix.run()
        tcp = TCPServerFactory(port=self.port)
        yield kernel.sigspawn, tcp.run()
        while True:
            # periodic housekeeping
            print "mark", time.time()
            kernel.info(kernel.ps())
            yield kernel.sigsleep, 10

    def gpgsetup(self):
        gnupghome = "%s/.gnupg" % self.varisconf
        gpg = GPG(gnupghome=gnupghome)
        if not gpg.list_keys(secret=True):
            host = socket.gethostname()
            genkeyinput = """
                Key-Type: RSA
                Key-Length: 1024
                Name-Real: ISdlink Server on %s
                Name-Comment: Created by %s
                Name-Email: isdlink@%s
                Expire-Date: 0
                %%commit
            \n""" % (host, sys.argv[0], host)
            gpg.gen_key(genkeyinput)

    def rpc822(self):
        """Serve all rpc822 requests from here"""
        server = rpc822.rpc822()
        # protocols we'll serve
        # XXX this is where we configure the stack
        # server.register('isfs1',isconf.ISFS1.ISFS1())
        # event queue we'll listen on
        yield kernel.sigalias, 'rpc822'
        while True:
            event = Event()
            # get the next request
            yield kernel.sigwait, event
            request = event.data
            # XXX get rid of the replyto business and use peer obj
            # instead?
            context  = event.context
            replyto = event.replyto 
            # call the method, get the response
            response = server.respond(request,context=context)
            # send the response back
            if not replyto:
                error("missing replyto")
                continue
            parties = kernel.event(replyto,response)
            if not parties:
                error("nobody listening on queue %s" % replyto)

class ServerFactory:

    def run(self,*args,**kwargs):
        global peers
        while True:
            yield None
            # accept new connections
            try:
                (peersock, address) = self.sock.accept()
                # XXX check if permitted address
                peer = Peer(role='slave')
                peers[peersock] = peer
                layer = ServerSocket(sock=peersock,address=address)
                peer.addLayer(layer)
                yield kernel.sigspawn, layer.run()
            except socket.error, (error, strerror):
                if not error == errno.EAGAIN:
                    raise
            
            # clean out dead peers
            for s in peers.keys():
                if peers[s].state() == 'down':
                    del peers[s]

class ServerSocket:
    """a TCP or UNIX domain server socket"""

    def __init__(self,sock,address,chunksize=4096):
        self.chunksize = chunksize
        self.sock = sock
        self.address = address
        self.role = 'master'
        self.state = 'up'
        self.txd = ''
        self.rxd = ''
        self.protocol = None
    
    def abort(self,msg=''):
        self.write(msg + "\n")
        self.close()

    def msg(self,msg):
        self.write(msg + "\n")

    def close(self):
        self.state = 'closing'

    # figure out what protocol to route the data to
    def dispatch(self,rxd):
        if verbose: print "dispatcher running"
        if '\n' not in rxd and len(rxd) > 128:
            self.abort("subab newline expected -- stop babbling")
            return 

        match = re.match("isconf(\d+)cli\n", rxd)
        if match and match.group(1) == '4':
            self.read(len(match.group())) # throw away this line
            self.protocol = isconf.ISconf4cli(self)
            kernel.spawn(self.protocol.start(self))
            if verbose: print "found isconf4cli"
            return 

        match = re.match("rpc822stream\n", rxd)
        if match:
            self.read(len(match.group())) # throw away this line
            self.protocol = Server.rpc822stream(self)
            kernel.spawn(self.protocol.start(self,address=self.address))
            if verbose: print "found rpc822stream"
            return 

        self.abort("supun protocol unsupported")

    def read(self,size):
        actual = min(size,len(self.rxd))
        if actual == 0:
            return ''
        rxd = self.rxd[:actual]
        # print "reading", rxd
        self.rxd = self.rxd[actual:]
        return rxd
    
    def write(self,data):
        # print "writing", repr(data)
        self.txd += data
    
    def run(self,*args,**kwargs):
        busy = False
        while True:
            if busy:
                yield kernel.sigbusy
            else:
                yield None
            # XXX peer timeout ck
            busy = False

            # find pending reads and writes 
            s = self.sock
            try:
                (readable, writeable, inerror) = \
                    select.select([s],[s],[s],0)
            except:
                inerror = [s]
        
            # handle errors
            if s in inerror or self.state == 'close':
                try:
                    s.close()
                except:
                    pass
                self.state = 'down'
                break

            # do reads
            if s in readable:
                # read a chunk
                try:
                    rxd = self.sock.recv(self.chunksize)
                except:
                    pass
                # print "receiving", rxd
                self.rxd += rxd
                if self.rxd:
                    busy = True
                else:
                    try:
                        s.shutdown(0)
                    except:
                        pass
                    self.state = 'closing'
                if self.state == 'up' and not self.protocol:
                    self.dispatch(self.rxd)

            # do writes
            if s in writeable:
                if len(self.txd) <= 0:
                    if self.state == 'closing':
                        self.state = 'close'
                    continue
                # print "sending", self.txd
                try:
                    sent = self.sock.send(self.txd)
                    # print "sent " + self.txd
                except:
                    try:
                        s.shutdown(1)
                    except:
                        pass
                    self.state = 'closing'
                if sent:
                    busy = True
                    # txd is a fifo -- clear as we send bytes off the front
                    self.txd = self.txd[sent:]
                
class TCPServerFactory(ServerFactory):

    def __init__(self, port, chunksize=4096):
        self.chunksize = chunksize
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        self.sock.setblocking(0)
        self.sock.bind(('', self.port))     
        self.sock.listen(5)
    
class UNIXServerFactory(ServerFactory):

    def __init__(self, path, chunksize=4096):
        self.chunksize = chunksize
        self.path = path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        self.sock.setblocking(0)
        if os.path.exists(self.path):
            os.unlink(self.path)
        self.sock.bind(self.path)
        self.sock.listen(5)
    
