
from __future__ import generators
import errno
import os
import select
import socket
import time
from isconf.Globals import *
from isconf.Kernel import kernel

class Timeout(Exception): pass

class ServerFactory:

    def run(self,out):
        """FBP component; emits ServerSocket refs on the 'out' pin""" 
        while True:
            yield None
            try:
                # accept new connections
                (peersock, address) = self.sock.accept()
                sock = ServerSocket(sock=peersock,address=address)
                yield kernel.sigspawn, sock.run()
                while not out.tx(sock): yield None
            except socket.error, (error, strerror):
                if not error == errno.EAGAIN:
                    raise
            
class ServerSocket:
    """a TCP or UNIX domain server socket"""

    def __init__(self,sock,address,chunksize=4096):
        self.chunksize = chunksize
        self.sock = sock
        self.address = address
        self.state = 'up'
        self.txd = ''
        self.rxd = ''
        self.protocol = None
    
    def __iter__(self):
        # reads one line at a time
        while True:
            if self.state == 'down':
                return
            nl = self.rxd.find("\n")
            if nl < 0:
                # raises StopIteration if more data needed
                return
            nl += 1
            rxd = self.rxd[:nl]
            self.rxd = self.rxd[nl:]
            yield rxd

    def abort(self,msg=''):
        self.write(msg + "\n")
        self.close()

    def msg(self,msg):
        self.write(msg + "\n")

    def close(self):
        self.state = 'closing'

    def read(self,size):
        # XXX also see MSG_PEEK flag in recv(2)
        actual = min(size,len(self.rxd))
        if actual == 0:
            return ''
        # print repr(actual)
        rxd = self.rxd[:actual]
        # print "reading", rxd
        self.rxd = self.rxd[actual:]
        return rxd
    
    def write(self,data):
        # print "writing", repr(data)
        self.txd += data
    
    def shutdown(self):
        self.sock.shutdown(1)

    def run(self):
        busy = False
        while True:
            if self.state == 'down':
                break
            if busy:
                yield kernel.sigbusy
            else:
                yield kernel.signice,10
            busy = self.txrx()

    def txrx(self):
        busy = False

        # find pending reads and writes 
        s = self.sock
        try:
            (readable, writeable, inerror) = \
                select.select([s],[s],[s],0.01)
        except Exception, e:
            debug("socket exception", e)
            inerror = [s]
    
        # handle errors
        if s in inerror or self.state == 'close':
            try:
                s.close()
            except:
                pass
            self.state = 'down'
            return

        # do reads
        if s in readable:
            rxd = ''
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

        # do writes
        if s in writeable:
            if len(self.txd) <= 0:
                if self.state == 'closing':
                    self.state = 'close'
                return
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
                return
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
        info("TCP server listening on port %d" % port)
    
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
        # until we have gpg auth in place...
        os.chmod(self.path,0600)
        info("UNIX domain server listening at %s" % path)
    
class UNIXClientSocket:
    """a blocking UNIX domain client socket"""

    def __init__(self, path, chunksize=4096):
        self.chunksize = chunksize
        self.ctl = path
        self.state = 'up'
        self.txd = ''
        self.rxd = ''
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.setblocking(1)
        debug("connecting to %s" % self.ctl)
        self.sock.connect(self.ctl)
        self.timeout = None

    def close(self):
        self.sock.close()

    def read(self,size):
        rxd = ''
        s = self.sock
        while len(rxd) < size:
            # debug("UNIXClientSocket select")
            (readable, writeable, inerror) = \
                select.select([s],[],[s],self.timeout)
            # do reads
            if s in readable:
                # debug("UNIXClientSocket readable")
                newrxd = self.sock.recv(size - len(rxd))
                if not newrxd:
                    return rxd
                rxd += newrxd
                return rxd
            # handle timeout
            raise Timeout

    def write(self,txd):
        sent = 0
        while sent < len(txd):
            sent += self.sock.send(txd[sent:])
        return sent

    def shutdown(self):
        self.sock.shutdown(1)

class UDPClientSocket:
    """a non-blocking UDP client socket"""

    def __init__(self, port):
        self.port = port
        self.txd = ''
        self.rxd = ''
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(0)
        debug("UDP client on port %s" % self.port)

