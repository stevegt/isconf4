
from __future__ import generators
from cStringIO import StringIO
import email.Message
import email.Parser
import email.Utils
import hmac
import inspect
import re
import sha
import sys
import time
import types

class fbp822:
    """Flow-based messages via simple RFC-822-like format.  

    Provides a faster and more binary-data-friendly mechanism than
    BoulderIO, XML, or MIME.  Message type goes in _type header,
    string parms go in other headers, binary payload goes in message
    body.  Obviously, this only gives us one payload, but that's the
    price we pay for speed and simplicity.  If you want multipart (and
    slower), then nest multiple fbp822 messages in the same payload,
    or (even slower) use XML or MIME.

    Optionally does HMAC -- see the following examples.

    For more information on how fbp822 can be used, Google for "flow
    based programming" and "data flow programming".

    >>> factory = fbp822()
    >>> msg = factory.mkmsg('apple')
    >>> 
    >>> msg.hmac_claimed()
    >>> msg.get_payload()
    ''
    >>> factory.parse(str(msg)).get_payload()
    ''
    >>> msg.hmacset('somekey')
    '5528934b82b37f57600eb8b2fb37cc9d591033a1'
    >>> assert msg.hmacok('somekey')
    >>> factory = fbp822(authkey='somekey')
    >>> msg = factory.mkmsg('puke green',
    ...     apple='red',Is=True,notis=False,answer=42)
    >>> assert not msg.hmacok('foo')
    >>> assert msg.hmacok('somekey')
    >>> assert msg['apple'] == 'red'
    >>> assert msg.head.apple == 'red'
    >>> msg = factory.parse(str(msg))
    >>> assert msg.head.notis is False
    >>> assert msg.head.notis is not True
    >>> assert msg.head.Is is True
    >>> assert msg.head.Is is not False
    >>> assert msg.head.answer is 42

    """


    def __init__(self,authkey=None):
        self.parser = email.Parser.Parser(Message)
        self.authkey = authkey

    def mkmsg(self,type,_payload='',**kwargs):
        msg = Message()
        msg.add_header('_type',type)
        if _payload is not None:
            _payload=str(_payload)
            msg.set_payload(_payload)
            msg.add_header('_size',str(len(_payload)))
        else:
            msg.add_header('_size',str(0))
        for (var,val) in kwargs.items():
            if var.startswith("_"):
                raise Error822("parameter names can't start with '_'")
            msg.setheader(var,val)
        if self.authkey:
            msg.hmacset(self.authkey)
        return msg

    msg = mkmsg

    def parse(self,txt,trial=False,maxheaderlen=65536):
        """Parse an fbp822 message.
        
        Returns the message object itself.
        
        This parser is intended to be used to test messages for
        completeness: 'trial', if True, means throw Incomplete822 if
        the message isn't all there, otherwise only throw exceptions
        in case of messages which are complete but bad.  
        
        >>> factory = fbp822()
        >>> msg = factory.mkmsg('apple','abc\\n123\\nxyz\\n',color='red')
        >>> factory.__class__.__name__
        'fbp822'
        >>> toolong = 'x' * 65537
        >>> factory.parse(toolong)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Error822: unable to parse
        >>> factory.parse(toolong,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Error822: headers too long: maxheaderlen exceeded
        >>> blankline = str(msg).find('\\n\\n')
        >>> partial = str(msg)[:blankline-1]
        >>> factory.parse(partial)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Error822: payload size mismatch: stated 12, actual 0
        >>> factory.parse(partial,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Incomplete822: 1
        >>> partial = str(msg)[:blankline+1]
        >>> factory.parse(partial,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Incomplete822: 1
        >>> partial = str(msg)[:blankline+2]
        >>> factory.parse(partial,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Incomplete822: 12
        >>> partial = str(msg)[:blankline+4]
        >>> factory.parse(partial,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Incomplete822: 10
        >>> partial = str(msg)[:blankline+14]
        >>> factory.parse(partial,trial=True).get_payload()
        'abc\\n123\\nxyz\\n'

        """

        txt = str(txt) # in case we were passed e.g. a StringIO() instance
        msg = self.parser.parsestr(txt)
        if not msg and txt.find('\n\n') > 0:
            raise Error822("malformed headers")
        try:
            if not msg:
                raise Error822("unable to parse")
            if not msg.has_key('_type'):
                raise Error822("missing _type header")
            type = msg['_type']
            if not type:
                raise Error822("empty _type header")
            if not msg.has_key('_size'):
                raise Error822("missing _size header")
            try:
                size = int(msg['_size'])
            except:
                raise Error822("invalid _size value")
            if size < 0: 
                raise Error822("invalid _size value")
        except Error822, e:
            if trial:
                if len(txt) > maxheaderlen:
                    raise Error822("headers too long: maxheaderlen exceeded")
                raise Incomplete822(1)
            raise Error822(e)
        payload = msg.get_payload()
        actsize = len(payload)
        if trial:
            if txt.find('\n\n') <= 0:
                raise Incomplete822(1)
            if actsize < size:
                raise Incomplete822(size - actsize)
        if actsize != size:
            # print repr(payload)
            raise Error822(
                "payload size mismatch: stated %d, actual %s" %
                (size,actsize)
                )
        return msg

    def fromStream(self,stream,outpin=None,intask=True):
        """generate message objects from a file or isconf.Socket
        
        If outpin is set, then use FBP Bus API, otherwise act as ordinary
        generator, yielding messages.
        
        """
        rxd = ''
        wanted = 1
        # read one message each time through complete loop
        factory = fbp822()
        i = 0
        while True:
            if intask:
                yield None
            if hasattr(stream,'state') and stream.state == 'down':
                if outpin: outpin.close()
                break
            newrxd = stream.read(wanted)
            # if isinstance(stream,file) and not len(newrxd):
            if not len(newrxd):
                # at EOF
                if outpin: 
                    outpin.close()
                break
            rxd += newrxd
            # discard leading newlines
            if rxd == '\n':
                rxd = ''
                continue
            # try to parse a message
            try:
                msg = factory.parse(rxd,trial=True)
            except Incomplete822, e:
                # nope, didn't get it all
                wanted = int(str(e))
                continue
            # yay. got it all
            if outpin is not None:
                while not outpin.tx(msg): yield None
            else:
                yield msg
            rxd = ''
            wanted = 1
        if rxd:
            # hmm.  junk at end of stream.  XXX discard for now
            pass

    def fromFile(self,stream,outpin=None,intask=True):
        """generate message objects from a file-like object

        higher performance than fromStream
        
        If outpin is set, then use FBP Bus API, otherwise act as ordinary
        generator, yielding messages.
        
        """
        rxd = ''
        total = 0
        # read one message each time through complete loop
        factory = fbp822()
        i = 0
        (START,HEAD,PARSE,BODY,SEND) = range(5)
        state=START
        for line in stream:
            if intask:
                yield None
            if state is START:
                # discard leading newlines
                if line == '\n':
                    continue
                if line.startswith("From "):
                    state = HEAD
            rxd += line
            if state is HEAD:
                if line == '\n':
                    state = PARSE
                else:
                    continue
            if state is BODY:
                if len(rxd) < total:
                    continue
                if len(rxd) > total:
                    print rxd, total
                    break
                state = PARSE
            if state is PARSE:
                # try to parse a message
                try:
                    msg = factory.parse(rxd,trial=True)
                    state = SEND
                except Incomplete822, e:
                    # nope, didn't get it all
                    print e
                    total = int(str(e)) + len(rxd)
                    state = BODY
                    continue
                except Exception, e:
                    print e
                    break
            if state is SEND:
                # yay. got it all
                if outpin is not None:
                    while not outpin.tx(msg): yield None
                else:
                    yield msg
                rxd = ''
                total = 0
                state = START
                continue
            print >>sys.stderr, "unidentified line:", line

        if rxd:
            print >>sys.stderr, "junk found at end of stream:", rxd
        if outpin: 
            outpin.close()



class Message(email.Message.Message):

    def __init__(self):
        email.Message.Message.__init__(self)
        date = time.ctime()
        self.set_unixfrom('From fbp822 %s' % (date))
        self.head = Head(self)

    def data(self):
        return self.get_payload()

    def ok(self):
        return self['_status'] == 'ok'

    def size(self):
        return self['_size']

    def type(self):
        return self['_type']

    def payload(self,data=None):
        if data is not None:
            self.set_payload(data)
            del self['_size']
            self['_size'] = str(len(data))
        return self.get_payload()

    def setheader(self,var,val):
        if self.has_key(var):
            del self[var]
        self[var] = str(val)
        # identify non-string types
        # if isinstance(val,types.BooleanType): # doesn't work in 2.2
        if val is True or val is False:
            self.add_header("_type_%s" % var,"b")
        elif isinstance(val,types.IntType):
            self.add_header("_type_%s" % var,"i")

    def hmac_calculated(self,key):
        h = hmac.new(key,msg=self.as_string(),digestmod=sha)
        digest = h.hexdigest()
        return digest

    def hmac_claimed(self):
        fromline = self.get_unixfrom()
        # print repr(self),fromline
        match = re.search("HMAC=([a-f0-9]+)",fromline)
        if not match:
            return None
        return match.group(1)

    def hmacok(self,key):
        claimed = self.hmac_claimed()
        wanted = self.hmac_calculated(key)
        return wanted == claimed

    def hmacset(self,key):
        digest = self.hmac_calculated(key)
        date = time.ctime()
        self.set_unixfrom('From fbp822 %s HMAC=%s' % (date,digest))
        return digest

    def as_string(self, unixfrom=0):
        """Return the entire formatted message as a string.
        Optional `unixfrom' when true, means include the Unix From_ envelope
        header.

        Overridden from email.Message in order to turn off
        mangle_from_.
        """
        from email.Generator import Generator
        fp = StringIO()
        g = Generator(fp,mangle_from_=False)
        g.flatten(self, unixfrom=unixfrom)
        return fp.getvalue()

class Head:

    def __init__(self,msg):
        self.__msg = msg

    def __getattr__(self,var):
        val = self.__msg[var]
        type = self.__msg.get("_type_%s" % var, '')
        if type == 'b':
            val.strip()
            if val == '1' or val == 'True':
                val = True
            if val == '0' or val == 'False':
                val = False
        if type == 'i':
            val.strip()
            val = int(val)
        return val

class Error822(Exception): pass
class Incomplete822(Exception): pass


