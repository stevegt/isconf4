
# XXX remove more extraneous code so it won't have to be audited


"""
Derived from Keith Dart's ipv4.py

Helper functions:

itodq(int) - return dotted quad string given an integer.
dqtoi(string) - return and integer given a string in IP dotted-quad notation.
iprange(startip, number) - return a list of sequential hosts in a network, as strings.
ipnetrange(startnet, number) - return a list of sequential networks, as strings.
netrange(startnet, number, [increment]) - return a list of networks, as IPv4 objects.

The IPv4 class stores the IP address and mask. It also makes available
the network, host, and broadcast addresses via psuedo-attributes.  


    >>> ip = IPv4("172.22.4.1/24")
    >>> ip
    IPv4('172.22.4.1/24')
    >>> ip.address
    '172.22.4.1'
    >>> ip.CIDR
    '172.22.4.1/24'
    >>> ip.address = "172.22.4.2/24"
    >>> ip.address
    '172.22.4.2'
    >>> dqtoi(ip.address)
    2887123970L
    >>> ip.CIDR
    '172.22.4.2/24'
    >>> ip.address = -1407843325
    >>> ip.CIDR
    '172.22.4.3/24'

"""

# for the address translation functions
import socket

class IPv4(object):
    """
    Store an IP address. Computes the network, host, and broadcast address on
    demand.

    Usage:
    ipaddress = IPv4(address, [mask])

    XXX Supply an address as an integer,  dotted-quad string, list of 4
    integer octets, or another IPv4 object. A netmask may optionally be
    supplied. It defaults to a classful mask appropriate for its class.
    the netmask may be supplied as integer, dotted quad, or slash (e.g.
    /24) notation. The mask may optionally be part of the IP address, in
    slash notation. if an IPv4 object is initialized with another IPv4
    object, the address and mask are taken from it. In the case that a
    mask is obtained from the address parameter, the mask parameter will
    be ignored.

    >>> ip = IPv4("10.1.1.2")
    >>> ip
    IPv4('10.1.1.2/8')
    >>> ip = IPv4("10.1.1.2", "255.255.255.0")
    >>> ip
    IPv4('10.1.1.2/24')
    >>> ip = IPv4("10.1.1.2/24") 
    >>> ip
    IPv4('10.1.1.2/24')

    Raises ValueError if the string representation is malformed, or is not an
    integer.

    Class attributes that you may set or read are:
        address   = 32 bit integer IP address
        mask      = 32 bit integer mask
        maskbits  = number of bits in the mask

    additional attributes that are read-only (UNDEFINED for /32 IPV4 objects!):
        network                = network number, host part is zero.
        host (or hostpart)    = host number, network part is zero.
        broadcast            = directed broadcast address, host part is all ones.
        firsthost            = What would be the first address in the subnet.
        lasthost            = What would be the last address in the subnet.

    Methods:
        copy() - Return a copy of this IPv4 address.
        nextnet() - Increments the IP address into the next network range.
        previousnet() - Decrements the IP address into the previous network range.
        nexthost() - Increments this IP address object's host number.
        previoushost() - Decrements this IP address object's host number.
        set_to_first() - Set the IP address to the first address in the subnet.
        set_to_last() - Set the IP address to the last address in the subnet.
        getStrings() - return a 3-tuple of address, mask and broadcast as dotted 
                       quad strings.

    Operators:
        An IPv4 object can be used in a "natural" way with some python
        operators.    It behaves as a sequence object when sequence
        operators are applied to it.
    
        >>> ip = IPv4("192.168.1.0", "255.255.255.248")
        >>> ip[2] # returns 2nd host in subnet.
        IPv4('192.168.1.2/29')
        >>> itodq(ip[2].address)
        '192.168.1.2'
        >>> ip[-1] # returns broadcast address.
        IPv4('192.168.1.7/29')
        >>> itodq(ip[-1].address)
        '192.168.1.7'
        >>> ip[0] # returns network.
        IPv4('192.168.1.0/29')
        >>> ip[1:-1] # returns list of IPv4 objects from first to last host.
        [IPv4('192.168.1.1/29'), IPv4('192.168.1.2/29'), IPv4('192.168.1.3/29'), IPv4('192.168.1.4/29'), IPv4('192.168.1.5/29'), IPv4('192.168.1.6/29')]
        >>> len(ip) # returns number of addresses in network range
        8
        >>> for i in ip:
        ...     print i
        192.168.1.1
        192.168.1.2
        192.168.1.3
        192.168.1.4
        192.168.1.5
        192.168.1.6
        >>> '192.168.1.2' in ip
        1
        >>> ip2 = ip + 2 
        >>> ip2
        IPv4('192.168.1.2/29')
        >>> ip2 > ip # returns true (can compare addresses)
        1
        >>> int(ip) # return IPv4 object address as integer
        -1062731520
        >>> hex(ip) # return IPv4 object address as hexadecimal string
        '0xc0a80100'

    """
    def __init__(self, address, mask=None):
        # determine input type and convert if necessary
        self._address = 0x0; self._mask = None
        self.__handleAddress(address)
        # handle the optional mask parameter. Default to class mask.
        if self._mask is None:
            if mask is None:
                if self._address & 0x80000000L == 0:
                    self._mask = 0xff000000L
                elif self._address & 0x40000000L == 0:
                    self._mask = 0xffff0000L
                else: 
                    self._mask = 0xffffff00L
            else:
                 self.__handleMask(mask)
        
    def __repr__(self):
        return "%s('%u.%u.%u.%u/%u')" % (self.__class__.__name__, (self._address >> 24) & 0x000000ff, 
                            ((self._address & 0x00ff0000) >> 16), 
                            ((self._address & 0x0000ff00) >> 8), 
                            (self._address & 0x000000ff), 
                            self.__mask2bits())

    def __str__(self):
        return "%u.%u.%u.%u" % ((self._address >> 24) & 0x000000ff, 
                            ((self._address & 0x00ff0000) >> 16), 
                            ((self._address & 0x0000ff00) >> 8), 
                            (self._address & 0x000000ff))

    def __getstate__(self):
        return (self._address, self._mask)
    
    def __setstate__(self, state):
        self._address, self._mask = state

    def __iter__(self):
        return _NetIterator(self)
    
    def __hash__(self):
        return self._address

    def getStrings(self):
        """getStrings() 
Returns a 3-tuple of address, mask, and broadcast address as dotted-quad string. 
        """
        return itodq(self._address), itodq(self._mask), itodq(self.broadcast)
    address_mask_broadcast = property(getStrings)
    
    def cidr(self):
        """cidr() Returns string in CIDR notation."""
        return "%s/%u" % (itodq(self._address), self.__mask2bits())

    CIDR = property(cidr)

    address = property(lambda s: itodq(s._address), 
            lambda s, v: s.__handleAddress(v), 
            None, "whole address")
    mask = property(lambda s: s._mask,
            lambda s, v: s.__handleMask(v),
            None, "address mask")
    maskbits = property(lambda s: s.__mask2bits(),
            lambda s, v: s.__handleMask(s.__bits2mask(v)),
            None, "CIDR mask bits")

    network = property(lambda s: IPv4(s._address & s._mask, s._mask),
            None, None, "network part")

    def _get_broadcast(self):
        if self._mask == 0xffffffffL:
            return 0xffffffffL
        else:
            return self._address | (~self._mask)
    broadcast = property(_get_broadcast)

    def _get_hostpart(self):
        # check for host specific address
        if self._mask == 0xffffffffL:
            return self._address
        else:
            return self._address & (~self._mask)
    def _set_hostpart(self, value):
        self._address = (self._address & self._mask) | (int(value) & ~self._mask)
    host = property(_get_hostpart, _set_hostpart, None, "host part")
    hostpart = host

    firsthost = property(lambda s: IPv4((s._address & s._mask) + 1, s._mask),
            None, None, "first host in range")

    lasthost = property(lambda s: IPv4((s._address & s._mask) + (~s._mask - 1), s._mask),
            None, None, "last host in range")

    def __int__(self):
        return self._address

    def __hex__(self):
        return hex(self._address)

    # The IPv4 object can be initialized a variety of ways.
    def __handleAddress(self, address):
        # determine input type and convert if necessary
        if type(address) is str:
            # first, check for optional slash notation, and handle it.
            aml = address.split("/")
            if len(aml) > 1:
                self._address = nametoi(aml[0])
                self._mask = self.__bits2mask(int(aml[1]))
            else:
                self._address = nametoi(aml[0])
        elif type(address) is int:
            self._address = address
        elif type(address) is list: # a list of integers as dotted quad (oid)
            assert len(address) >= 4
            self._address = (address[0]<<24) | (address[1]<<16) | (address[2]<<8) | address[3]
        elif isinstance(address, IPv4):
            self._address = address._address
            self._mask = address._mask
        else:
            raise ValueError

    def __handleMask(self, mask):
        if type(mask) is str:
            if mask[0] == '/':
                bits = int(mask[1:])
                self._mask = self.__bits2mask(bits)
            elif mask == "255.255.255.255": # special case since aton barfs on this
                self._mask = 0xffffffffL
            else:
                self._mask = dqtoi(mask)
        elif type(mask) is int:
            self._mask = mask
        else:
            raise ValueError

    def __bits2mask(self, bits):
        if bits <= 32 and bits >= 0:
            return 0xffffffffL << (32 - bits)
        else:
            raise ValueError
        
    def __mask2bits(self):
        # Try to work around the fact the in Python, right shifts are always
        # sign-extended 8-( Also, cannot assume 32 bit integers.
        val = self._mask
        bits = 0
        for byte in range(4):
            testval = (val >> (byte * 8)) & 0xff
            while (testval != 0):
                if ((testval & 1) == 1):
                    bits = bits + 1
                testval = testval >> 1
        return bits

    def __add__(self, increment):
        return IPv4(self._address + increment, self._mask)

    def __sub__(self, decrement):
        return IPv4(self._address - decrement, self._mask)

    def __cmp__(self, other):
        return cmp(self._address, other._address)

    def __contains__(self, other):
        other = self.__class__(other)
        # if self._mask != other._mask:
        #     return 0
        return (self._address & self._mask) == (other._address & other._mask)

    # By defining these sequence operators, an IPv4 object can appear as a
    # "virtual" sequence of IPv4 objects. 
    # e.g.: ip[4] will return the 4th host in network range. ip[-1] will
    # return the last. Note that ip[0] returns the network, and ip[-1]
    # returns the broadcast address.
    def __getitem__(self, index):
        if index >= 0:
            print index, self._mask, ~self._mask
            if index <= ~self._mask:
                return IPv4((self._address & self._mask) + index, self._mask)
            else:
                raise IndexError, "Host out of range"
        else:
            if -index <= ~self._mask + 1:
                return IPv4((self._address & self._mask) + (~self._mask + index + 1), self._mask)
            else:
                raise IndexError, "Host out of range"

    def __setitem__(self, index, value):
        raise IndexError, "cannot set a sequence index"

    # len(ip) is number of hosts in range, including net and broadcast
    def __len__(self):
        return ~self._mask + 1

    # this is slightly wrong. A slice returns a real list of IPv4 objects,
    # not another IPv4 object.
    def __getslice__(self, start, end):
        length = ~self._mask + 1
        selfnet = self._address & self._mask
        if end < 0:
            end = length + end
        if start < 0:
            start = length + start
        start = min(start, length)
        end = min(end, length)
        sublist = []
        for i in xrange(start, end):
            sublist.append(IPv4(selfnet + i, self._mask))
        return sublist

    def copy(self):
        return IPv4(self._address, self._mask)

    def __isub__(self, other):
        self._address = self._address - other
        # if host becomes broadcast address, bump it to next network
        if self.host == ~self.mask:
            self._address = self._address - 2
        return self

    def __iadd__(self, other):
        self._address = self._address + other
        # if host becomes broadcast address, bump it to next network
        if self.host == ~self.mask:
            self._address = self._address + 2
        return self
    
    def nexthost(self, increment=1):
        """
Increments this IP address object's host number. It will overflow into the
next network range. It will not become a broadcast or network address.

        """
        self._address = self._address + increment
        # if host becomes broadcast address, bump it to next network
        if self.host == ~self.mask:
            self._address = self._address + 2
        return self

    def previoushost(self, decrement=1):
        """
Decrements this IP address object's host number. It will underflow into the
next network range. It will not become a broadcast or network address.

        """
        self._address = self._address - decrement
        # if host becomes broadcast address, bump it to next network
        if self.host == ~self.mask:
            self._address = self._address - 2
        return self

    def set_to_first(self):
        """
Set the address to the first host in the network.
        """
        self._address = (self._address & self._mask) + 1
        return self

    def set_to_last(self):
        """
Set the address to the last host in the network.
        """
        self._address = (self._address & self._mask) + (~self._mask - 1)
        return self

    def nextnet(self, increment=1):
        """
Increments the IP address into the next network range, keeping the host
part constant. Default increment is 1, but optional increment parameter
may be used.

        """
        self._address = self._address + (~self._mask+1) * increment
        return self

    def previousnet(self, decrement=1):
        """
Decrements the IP address into the next network range, keeping the host
part constant. Default decrement is 1, but optional decrement parameter
may be used.

        """
        self._address = self._address - (~self._mask+1) * decrement
        return self

    def gethost(self):
        """gethost()
    Resolve this IP address to a canonical name using gethostbyaddr."""
        try:
            hostname, aliases, others = socket.gethostbyaddr(str(self))
        except:
            return ""
        return hostname
    hostname = property(gethost, None, None, "associated host name")

##### end IPv4 object #########

class _NetIterator(object):
    def __init__(self, net):
        mask = self.mask = net._mask
        self.start = (net._address & mask)
        self.end = (net._address & mask) + (~mask - 1)

    def __iter__(self):
        return self
    
    def next(self):
        if self.start == self.end:
            raise StopIteration
        self.start += 1
        return IPv4(self.start, self.mask)

### Useful helper functions. May also be useful outside this module. ###

def nametoi(name):
    """Resolve a name and return the IP address as an integer."""
    return dqtoi(socket.gethostbyname(name))

def dqtoi(dq):
    """dqtoi(dotted-quad-string)
Return an integer value given an IP address as dotted-quad string. You can also
supply the address as a a host name. """
    s = buffer(socket.inet_aton(dq))
    return (ord(s[0]) << 24L) + (ord(s[1]) << 16L) + (ord(s[2]) << 8L) + (ord(s[3]))

def itodq(addr):
    """itodq(int_address) (integer to dotted-quad)
Return a dotted-quad string given an integer. """
    intval = int(addr) # might get an IPv4 object
    s = "%c%c%c%c" % (((intval >> 24) & 0x000000ff), ((intval & 0x00ff0000) >> 16),
        ((intval & 0x0000ff00) >> 8), (intval & 0x000000ff))
    return socket.inet_ntoa(s)

def iprange(startip, number, increment=1):
    """
iprange: return a list of consequtive IP address strings.
Usage:
    iprange(startip, number)
Where:
    startip is an IP address to start from.
    number is the number of IP addresses in the returned list.
    """
    # make a copy first
    start = IPv4(startip)
    ips = []
    for i in xrange(number):
        ips.append(str(start))
        start.nexthost(increment)
    return ips


def ipnetrange(startnet, number, increment=1):
    """
ipnetrange: return a list of consecutive networks, starting from initial
network and mask, keeping the mask constant.
Usage:
    ipnetrange(startnet, number, [increment])
Where:
    startnet is an IP address where the range will start.
    number is the number of IP networks in the range
    optional increment will skip that number of nets.

    """
    start = IPv4(startnet)
    ips = []
    baseaddress = start.address
    for i in xrange(number):
        start.address = baseaddress + (~start.mask+1) * (i*increment)
        ips.append(str(start))
    return ips
    
def netrange(startnet, number, increment=1):
    """
netrange: return a list of consecutive networks, starting from initial
network and mask, keeping the mask constant.
Usage:
    netrange(startnet, number, [increment])
Where:
    startnet is an IP address where the range will start.
    number is the number of IP networks in the range.
    An optional increment will set the stride (count by <increment> nets).

    """
    ips = []
    counter = IPv4(startnet)
    for i in xrange(number):
        ips.append(counter.copy())
        counter.nextnet(increment)
    return ips
    

def resolve(host, mask=None):
    """resolve(hostname, [mask]
Resolve a hostname to an IPv4 object. An optional mask value may me supplied."""
    try:
        hostname, aliases, addresses = socket.gethostbyname_ex(str(host))
    except socket.gaierror, why:
        raise ValueError, "Unable to resolve host: %s" % (why[1])
    if addresses:
        return IPv4(addresses[0], mask)
    else:
        raise ValueError, "No addresses found."


