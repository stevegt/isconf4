# vim:set expandtab:
# vim:set foldmethod=indent:
# vim:set shiftwidth=4:
# vim:set tabstop=4:

from __future__ import generators
import ConfigParser
import copy
import email.Message
import email.Parser
import errno
import inspect
import md5
import os
import popen2
import random
import re
import select
import sha
import shutil
import socket
import sys
import time
import isconf
from isconf.Globals import *
from isconf.GPG import GPG
from isconf.Kernel import kernel
from isconf.Protocol import Protocol

# XXX inherit from email.Message -- just use our own parser
class XXXISdlink1Message:
    """an ISdlink1 message"""

    msgcat = {
        'dahek': 'hereis public key',
        'datem': 'text encrypted message ',
        'decry': 'bad encryption, cannot decrypt with my key',
        'dedis': 'message dispatch error',
        'dehed': 'no message headers found',
        'sepun': 'protocol unsupported',
        'desig': 'bad signature, cannot verify with your key',
        'dukey': 'key import failed',
        'sibye': 'please disconnect',
        'sisek': 'send public key',
        'subab': 'excessive line length -- stop babbling ',
        'subak': 'bad public key, aborting',
        'sumal': 'malformed message, aborting',
        'sumes': 'message expected',
        'sunek': 'need your public key first, aborting',
        'supun': 'protocol unsupported',
        'surec': 'bad rectype',
        'susiz': 'missing message size',
        'susrv': 'server error',
    }

    def __init__(self,controller,rectype=None,payload=None,info=None):
        self.controller = controller
        self.rectype = rectype
        self.payload = payload
        self.info = info
        self.wiredata = ''
        self.headers = {}
        # for (var,val) in kwargs.items():
        #     setattr(self,var,val)

    def fromStream(self,rxd):
        self.wiredata = rxd
        # datem some info\n1234\n{data}
        m = re.match("^(\w+)(\s+(.*))?\n((\d+)\n([\s\S]*))?$",rxd)
        # check format
        if not m:
            if len(rxd) > 128:
                self.error('sumes')
                return -1
            return 1
        rectype = m.group(1)
        self.rectype = rectype
        # handle single-line messages
        if rectype[0] == 's':
            kernel.info("got single line message")
            return 0
        if rectype[0] != 'd':
            self.error('surec',info=rectype)
            return -1
        try:
            self.info = m.group(3)
            size = int(m.group(5))
            data = m.group(6)
        except:
            if len(rxd) > 128:
                self.error('susiz')
                return -1
            return 1
        # make sure we have the whole message
        if len(data) < size:
            return size - len(data)
        kernel.info("got multiline message")
        # handle messages sent in-clear
        if rectype in ('dahek', 'decry'):
            self.payload = data
            return 0
        # decrypt everything else
        if verbose: print "decrypting"
        try:
            data = gpgengine.decrypt(data)
        except Exception, e:
            self.error('decry',info=e)
            return -1
        # extract headers and body
        try:
            m = email.Parser.HeaderParser(data)
        except Exception, e:
            self.error('dehed', info=e)
            return -1
        head = m.group(1)
        self.payload = m.group(3)
        self.headers = {}
        print head
        while head:
            # matches a single RFC822-style "var: val" header,
            # including folding
            m = re.match("(\w+):[ \t]*(.*\n([ \t]+.*\n)*)([\s\S]*)$",head)
            if not m:
                self.error('dehed',info="malformed header",payload=head)
                return -1
            var = m.group(1)
            val = m.group(2).strip()
            head = m.group(4)
            self.headers[var] = val
        return 0

    def error(self,rectype,**kwargs):
        kernel.info("isdlink error: %s %s" % (rectype, str(kwargs)))
        if rectype[0] == 'd' and not kwargs.has_key('payload'):
            size = min(512,len(self.wiredata))
            kwargs['payload'] = self.wiredata[:size]
        self.reply(rectype,**kwargs)
        if rectype[1] == 'u':
            self.controller.stop()

    def reply(self,rectype,**kwargs):
        message = ISdlink1Message(
            controller=self.controller,
            rectype=rectype,
            **kwargs
            )
        message.send()

    def send(self,rectype=None):
        if rectype:
            self.rectype = rectype
        if not self.rectype:
            # XXX raise exception instead
            kernel.error("missing rectype: %s" % str(self))
            return
        self.controller.tx(self)

    def toString(self):
        rectype = self.rectype
        # create first line
        out = "%s %s" % (rectype, self.msgcat[rectype])
        if self.info:
            out += ": %s" % self.info
        out += "\n"
        if rectype[0] == 's':
            # single-line message
            return out
        if rectype == 'dahek':
            # send our public key
            key = gpgengine.showpubkey()
            out += str(len(key)) + "\n"
            out += key
            return out
        if rectype == 'decry':
            out += str(len(self.payload)) + "\n"
            out += self.payload
            return out
        # attach message headers and any content
        cleartext = ''
        # if self.payload:
        #     size = len(self.payload)
        #     self.headers['size'] = size
        for var in self.headers.keys():
            cleartext += "%s: %s\n" % (var,self.headers[var])
        if self.payload:
            cleartext += self.payload
        # encrypt 
        if cleartext:
            data = gpgengine.encrypt(cleartext,self.controller.fingerprint)
            out += "%d\n%s" % (len(data), data)
            return out
        out += "0\n"
        return out
    
class XXXISdlink1(Protocol):
    """
    protocol controller -- one per socket connection
    
    """

    def __init__(self,transport):
        # Protocol.__init__(self,transport)
        self.fingerprint = None


    def dispatch(self,message):
        rectype = message.rectype
        if rectype == 'sibye':
            kernel.info("got sibye")
            self.stop()
            return
        if rectype == 'sisek':
            if self.transport.role == 'master':
                message.error('sunek')
                return
            message.reply("dahek")
            return
        if rectype == 'dahek':
            kernel.info("it's a key")
            peerprints = gpgengine.import_keys(message.payload)
            try:
                # XXX move import_keys to here after debug
                pass
            except Exception,e:
                message.error('dukey',info=e)
                return
            fingerprint = peerprints[0]
            self.fingerprint = fingerprint
            self.route(fingerprint,self)
            if self.transport.role == 'master':
                message.reply("dahek")
            return
        if rectype == 'datem':
            # send to higher-level protocol
            try:
                protocol = message.headers['content']
            except:
                message.error('dehed',
                    info="no content header",
                    payload=str(message.headers)
                )
                return
            try:
                if protocol == 'rpc822':
                    kernel.event('rpc822',fromid=self)
            except Exception, e:
                message.error('dedis',info=e,payload=message.payload)
            return
            message.error('sepun',info=protocol)
            return
        # XXX raise exception instead
        kernel.error("unhandled rectype: %s" % rectype)
        message.error('surec',info=rectype)

class ISdlink1:

    def __init__(self):
        self.peers = {}
        self.rpc = rpc822.rpc822()
        self.call = self.rpc.call('isdlink1')

    def _auth(self,method,fromid):
        # rpc822 server always checks here before calling a method
        self.address = fromid
        self.peers.setdefault(self.fromid, {})
        if method in ('swapkeys'):
            # this is always allowed
            return True
        if self.peers[fromid].get('fingerprint',False):
            # gotta swap GPG keys first
            return False
        if method in ('login'):
            return True
        # everything else needs an HMAC
        return self.peers[fromid].get('authkey',False)
            
    def login(self):
        # we do HMAC inside of PGP encryption so that we get
        # end-to-end authentication
        return self.authkeys[method].get(fromid,self._mkkey())

    def _mkkey(self):
        # XXX might want more entropy...
        seed = "%d%s%f" % (os.getpid(),repr(self),time.time())
        random.Random(seed).random()

    def swapkeys(self,key):
        """exchange public keys"""
        peerprints = gpgengine.import_keys(key).fingerprints
        fingerprint = peerprints[0]
        self.peers[self.address]['fingerprint'] = fingerprint
        mykey = gpgengine.showpubkey()
        return mykey

    def dispatch(self,ciphertext):
        """process an encrypted message"""
        cleartext = gpgengine.decrypt(ciphertext)
        kernel.event('rpc822',cleartext,fromid=XXX)






    def decry(self,XXX):
        """bad encryption, cannot decrypt with my key"""
        pass

    def desig(self,XXX):
        """bad signature, cannot verify with your key"""
        pass

    def dukey(self,XXX):
        """key import failed"""
        pass

    def sibye(self,XXX):
        """please disconnect"""
        pass

    def subak(self,XXX):
        """bad public key, aborting"""
        pass

    def sunek(self,XXX):
        """need your public key first, aborting"""
        pass

    def susrv(self,XXX):
        """server error"""
        pass


