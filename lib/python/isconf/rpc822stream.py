# vim:set expandtab:
# vim:set foldmethod=indent:
# vim:set shiftwidth=4:
# vim:set tabstop=4:

from __future__ import generators
import copy
import os
import re
import sys
import time
import isconf
from isconf.Globals import *
from isconf.Kernel import kernel
import rpc822

class rpc822stream:
    """
    convert between stream-based transport and rpc822 messages
    
    """

    def __init__(self,transport,address):
        self.transport = transport
        self.address = address

    def rxloop(self,*args,**kwargs):
        rxd = ''
        wanted = 1
        # read one message each time through complete loop
        rpc = rpc822()
        while True:
            yield None
            if self.transport.state == 'down':
                return
            rxd += self.transport.read(wanted)
            # discard leading newlines
            if rxd == '\n':
                rxd = ''
                continue
            # try to parse a message
            try:
                msg = rpc.parse(rxd,trial=True)
            except Incomplete822, e:
                # nope, didn't get it all
                wanted = e
                continue
            except Error822, e:
                # sleep for a while to throttle bad peers and deter 
                # brute-force knob twisting
                yield kernel.sigsleep, 5
                # XXX try to keep connection alive instead of aborting
                self.transport.abort("sumal malformed message: %s" % e)
                return
            except Exception, e:
                kernel.error("message parsing exception: %s" % e)
                yield kernel.sigsleep, 5
                # XXX try to keep connection alive instead of aborting
                self.transport.abort("susrv server error, aborting")
                return
            # yay. got it all -- now post it to the event queue
            # XXX pass peer obj here instead of fromid?
            kernel.event('rpc822',msg,fromid=self.address)
            rxd = ''
            wanted = 1

    def start(self):
        kernel.info("starting rpc822stream")
        kernel.spawn(self.txloop())
        kernel.spawn(self.rxloop())

    def stop(self):
        self.transport.close()

    def txloop(self,*args,**kwargs):
        yield kernel.sigalias, self
        while True:
            if self.transport.state == 'down':
                self.stop()
                return
            event = Event()
            yield kernel.sigwait, event
            msg = event.data
            self.transport.write(str(msg))

