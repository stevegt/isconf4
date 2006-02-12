# vim:set expandtab:
# vim:set foldmethod=indent:
# vim:set shiftwidth=4:
# vim:set tabstop=4:

from __future__ import generators
import copy
import os
import sys
import time
import traceback

from isconf.Globals import *

class Deadlock(Exception): pass
class Restart(Exception): pass

class Bus:
    """
    
    >>> def mygen(name,inpin,outpin):
    ...     while True:
    ...         mlist = []
    ...         yield inpin.rx(mlist)
    ...         for msg in mlist:
    ...             msg = "%s got (%s)" % (name, msg)
    ...             while not outpin.tx(msg):
    ...                 print "waiting for readers"
    ...                 yield None
    >>>
    >>> def printer(inpin):
    ...     while True:
    ...         l = []
    ...         yield inpin.rx(l)
    ...         for j in l:
    ...             print j
    >>> 
    >>> bus1 = Bus()
    >>> bus2 = Bus()
    >>> bus3 = Bus(minreaders=2)
    >>> assert not bus1.tx('never')
    >>> t = kernel.spawn(bus1.writer('apple'))
    >>> a = kernel.spawn(mygen('alice',inpin=bus1,outpin=bus2))
    >>> b = kernel.spawn(mygen('bob',inpin=bus2,outpin=bus3))
    >>> r = kernel.spawn(bus3.reader(),itermode=True)
    >>> p = kernel.spawn(printer(inpin=bus3))
    >>> kernel.run(steps=100)
    bob got (alice got (apple))
    >>> bus1.tx('pear')
    1
    >>> kernel.run(steps=100)
    bob got (alice got (pear))
    >>> r.next()
    'EAGAIN'
    >>> kernel.run(steps=100)
    >>> r.next()
    'bob got (alice got (apple))'
    >>> kernel.run(steps=100)
    >>> r.next()
    'bob got (alice got (pear))'
    >>> kernel.run(steps=100)
    >>> r.next()
    'EAGAIN'
    
    """
    
    def __init__(self,maxlen=None,minreaders=1,name=None):
        self.maxlen = maxlen
        # all reader queues, indexed by task id
        self.readq = {}
        self.minreaders = minreaders
        self.name = name
        self.state = 'up'
    
    def busy(self):
        self.clean()
        for (tid,queue) in self.readq.items():
            if len(queue):
                return True
        return False

    def clean(self):
        for (tid,queue) in self.readq.items():
            if not kernel.isrunning(tid):
                del self.readq[tid]

    def close(self):
        self.state = 'down'

    def subscribe(self,tid):
        """Create a readers queue for tid.  Called by kernel."""
        self.readq.setdefault(tid,[])

    def tx(self,msg):
        if self.state == 'down':
            return 0
        self.clean()
        i = len(self.readq) # number of subscribed readers
        if i < self.minreaders:
            return False
        for (tid,queue) in self.readq.items():
            if self.maxlen and len(queue) + 1 > self.maxlen:
                raise Deadlock  # XXX need some id here
            queue.append(msg)
        return i

    def reader(self):
        """convenience generator -- read bus while not in a task"""
        while True:
            mlist = []
            yield self.rx(mlist)
            for msg in mlist:
                yield msg
    
    def writer(self,msg):
        """convenience generator -- reliable tx"""
        while not self.tx(msg):
            yield None
    
    def ready(self,tid,buf,expires,count):
        if len(self.readq[tid]):
            c = min(len(self.readq[tid]), count)
            buf += self.readq[tid][:c]
            self.readq[tid] = self.readq[tid][c:]
            return True
        if self.state == 'down':
            buf.append(kernel.eof)
            return True
        if (expires is not None) and time.time() > expires:
            buf.append(kernel.eagain)
            return True
        return False

    def rx(self,buf,timeout=None,count=999999):
        """

        >>> def cgen(inpin,count=99999):
        ...     while True:
        ...         mlist = []
        ...         yield inpin.rx(mlist,count=count)
        ...         print count, mlist
        ...
        >>> bus1 = Bus()
        >>> a = kernel.spawn(cgen(inpin=bus1))
        >>> b = kernel.spawn(cgen(inpin=bus1,count=1))
        >>> kernel.run(steps=1000)
        >>> bus1.tx(1)
        2
        >>> bus1.tx(2)
        2
        >>> bus1.tx(3)
        2
        >>> kernel.run(steps=1000)
        99999 [1, 2, 3]
        1 [1]
        1 [2]
        1 [3]

        """
        expires = None
        if timeout is not None:
            expires = time.time() + timeout
        # kernel will call subscribe()
        return kernel.sigrx, self, buf, expires, count

class Kernel:
    """

    Contains a scheduler, shared objects, messaging, logging, and
    related bits.

    This is a "weightless threads" scheduler, using Python generator
    objects as if they were threads -- we will call them 'tasks' here
    to avoid confusion.  Google for 'python weightless threads
    generators' for more information, and for more background google
    for 'continuations' and for 'coroutines'.  You can safely ignore
    mentions of stackless python microthreads -- they are
    something else entirely and require a special version of
    python.  
        
    At http://www.chiark.greenend.org.uk/~sgtatham/coroutines.html,
    Simon Tatham shows a really good example of why protocol stacks
    are a pain to write when you don't have something like threads,
    coroutines, continuations, or at least generators available.  
   
    Here we aren't quite emulating full-fledged coroutines or even
    continuations, but instead sticking with simple message-passing
    tasks because it's a familiar concept which translates directly
    from UNIX processes and SysV IPC, making the control flow easier
    to understand and debug. 

    Generator-based tasks are also more portable than using native
    Python threads, since Python threads aren't available on all
    versions of UNIX yet.  Of course this is less portable to other
    languages; if you're porting ISconf to Perl, for instance, you
    might use POE.  If you're porting to C, then you're probably stuck
    with native threads, or simulating coroutines with setjmp/longjmp,
    or worse yet, something like Simon's coroutine macro hacks
    described at the above URL.
    
    When writing this version of ISconf, I was tempted to use
    asyncore, which is the basis of both Zope and Twisted, and also
    tried hand-crafting my own event queue and select() loop, but kept
    running into the same issues Simon describes so succinctly.  I
    kept throwing away code until I finally gave in to the Force and
    started using generators instead -- *muuuch* better.   

    """

    # XXX yield should return object rather than string
    sigrx='rx'
    sigbusy='busy'
    signice='nice'
    sigret='ret'
    sigsleep='sleep'
    sigspawn='spawn'
    siguntil='until'
    eagain = 'EAGAIN'
    eof = 'EOF'

    def __init__(self):
        self._tasks = {}
        self._nextid = 1
        self.HZ = 1000
        self._shutdown = False

    def isdone(self,tid):
        return not self.isrunning(tid)

    def isrunning(self,tid):
        return self._tasks.get(tid,False)

    def kill(self,tid):
        debug("killing", tid)
        self._tasks.setdefault(tid,None)
        del self._tasks[tid]

    def abort(self,task,e):
        tid = task.tid
        exc_info = sys.exc_info()
        exc_type, exc_val, tb = exc_info[:3]
        out = traceback.format_exception(exc_type, exc_val, tb)
        out = ''.join(out)
        out = out.strip() + "\n"
        if task.errpin:
            task.errpin.tx(out)
        else:
            msg = "kernel: %s" % out
            error(msg)
            print >>sys.stderr, msg
            # XXX only restart task instead
            raise Restart
        self.kill(tid)

    def killall(self):
        tids = self._tasks.keys()
        for tid in tids:
            self.kill(tid)
        self._tasks = {}

    def shutdown(self):
        debug("shutting down")
        self._shutdown = True

    def ps(self):
        return self._tasks
        # XXX
        out = ''
        for id in self._tasks.keys():
            task = self._tasks[id]
            out += str(task) + "\n"
        return out

    def wait(self,genobj):
        """Spawn a task and wait for it to finish.  For example, if
        you do:
        
            yield kernel.wait(sometask())

        ...the yield will not return until sometask() completes.

        """
        return self.siguntil, self.spawn(genobj).isdone

    # XXX add respawn flag, only raise Restart if not set
    def spawn(self,genobj,itermode=False,name=None):
        """
        Let the kernel manage an ordinary generator object by wrapping
        it in a Task -- extremely powerful, because this means a yield
        in an ordinary generator will allow unrelated tasks to run.
        It also means ordinary generators can yield sig* values to
        talk to the kernel e.g. sigsleep.

        If itermode=False, then run freely, returning values only to the
        kernel, which is going to interpret them as control signals or
        throw them away if unrecognized.

        If itermode=True, then run in single-step mode and return each
        value to the caller like a normal generator.  The only unusual
        thing the caller needs to know is that if there is no result
        ready, then you will get a kernel.eagain result instead.  

        >>> def mygen():
        ...     i = 0
        ...     while True:
        ...         yield i
        ...         if i == 3: yield kernel.sigsleep,1
        ...         i += 1
        ... 
        >>> obj = kernel.spawn(mygen(),itermode=True)
        >>> kernel.run(steps=10)
        >>> obj.next()
        0
        >>> kernel.run(steps=10)
        >>> obj.next()
        1
        >>> kernel.run(steps=10)
        >>> obj.next()
        2
        >>> kernel.run(steps=10)
        >>> obj.next()
        3
        >>> kernel.run(steps=10)
        >>> obj.next()
        'EAGAIN'
        >>> kernel.run(steps=10)
        >>> obj.next()
        'EAGAIN'
        >>> while obj.next() != 4:
        ...         kernel.run(steps=10)
        ... 
        >>> kernel.run(steps=100)
        >>> obj.next()
        5
        >>> kernel.run(steps=100)
        >>> obj.next()
        6
        >>> obj.itermode=False
        >>> kernel.run(steps=100)
        >>> assert obj.next() > 10
        
        """

        task = Task(genobj,tid=self._nextid,name=name)
        tid = task.tid
        assert tid == self._nextid
        self._nextid += 1
        self._tasks[tid] = task
        task.itermode = itermode
        # immediately advance to the first yield; allows message bus
        # readers to subscribe right away; assumes bus.rx() is their
        # first yield
        self.step(task)
        return task

    def run(self, initobj=None, steps=None):
        """
        runs for {steps} or until init task is done
        
        """
        assert initobj or steps
        if initobj and not self.isrunning(1): 
            self.spawn(initobj)
        ticks = 0
        while True:
            if self._shutdown:
                sys.exit(0)
            if initobj and not self.isrunning(1): break
            if steps and steps <= ticks: 
                break
            ticks += 1
            # print self.HZ
            time.sleep(1/self.HZ)
            if not steps:
                self.HZ *= .99
            self.HZ = max(self.HZ,1)
            self.HZ = min(self.HZ,999999)
            # if self.HZ < 100:
            #     debug("HZ", self.HZ) 
            for tid in self._tasks.keys():
                task = self._tasks[tid]
                task.priority = min(task.priority, 10)
                # wait for N ticks if delay is set
                if task.delay > 1:
                    task.delay -= 1
                    continue
                task.delay += task.priority
                if task.sleep and task.sleepDone > time.time():
                    # slow down so we don't beat up time()
                    # XXX we can do a better job here -- use HZ and
                    # sleepDone to calculate delay more accurately
                    task.priority += 1
                    continue
                task.sleep = None
                # wait until condition is met
                if task.until:
                    done=False
                    try:
                        if isinstance(task.untilArgs,list) or \
                               isinstance(task.untilArgs,tuple):
                            done = task.until(*task.untilArgs)
                        elif task.untilArgs:
                            done = task.until(task.untilArgs)
                        else:
                            done = task.until()
                    except Exception, e:
                        # XXX add traceback
                        self.abort(task,e)
                        continue
                    if not done:
                        # slow down so we don't beat up until()
                        task.priority += 1
                        continue
                task.until = None
                if task.itermode and task.resultReady:
                    # we're waiting for Task.next() to pick up our
                    # previous result
                    task.priority += 1
                    continue
                self.step(task)

    def step(self,task):
        obj = task.obj
        tid = task.tid
        # debug("stepping task", tid)
        try:
            argv = obj.next()
        except StopIteration:
            self.kill(tid)
            return
        except ValueError, e:
            if e == 'generator already executing':
                # kernel.run() is nested -- that's okay to do
                return
            raise
        except Exception, e:
            # XXX add traceback
            self.abort(task,e)
            return
        # figure out why task yielded and what it wants
        targv = argv
        if not isinstance(targv,tuple):
            targv = (targv,)
        if targv:
            why = targv[0]
        if why != self.sigsleep and why != None:
            # print "why",why
            self.HZ *= 10
        sigargs = None
        if len(targv) > 1:
            sigargs = targv[1:]
        # XXX these should all be 'is' rather than '=='
        if why == self.sigbusy:
            task.nice -= 1
            if task.nice < 0: 
                task.nice = 0
        elif why == self.signice:
            task.nice = sigargs[0]
        elif why == self.sigsleep:
            task.sleep = sigargs[0]
            task.sleepDone = time.time() + task.sleep
        elif why == self.sigspawn:
            genobj = sigargs[0]
            spawnargs = None
            if len(sigargs) > 0:
                spawnargs = sigargs[1:]
            self.spawn(genobj)
        elif why == self.siguntil:
            task.until = sigargs[0]
            if len(sigargs) > 1:
                task.untilArgs = sigargs[1:]
            else:
                task.untilArgs = None
        elif why == self.sigrx:
            bus = sigargs[0]
            buf = sigargs[1]
            args = sigargs[2:]
            task.until = bus.ready
            task.untilArgs = [tid,buf] + list(args)
            bus.subscribe(tid)
        elif why == self.sigret:
            task.context.ret()
        else:
            # we got an ordinary value back -- save it for itermode
            task.result = argv
            task.resultReady = True
        task.priority = (task.priority + task.nice) / 2

class Task:
    """
    A "weightless thread" representing a generator object.
    
    XXX stop passing in parent -- we can tell who the parent task
    is, even if a few stack frames away, e.g.:

    s = inspect.stack()
    s[1][0]
    <frame object at 0x82ba4a4>
    genobj.gi_frame
    <frame object at 0x82ba4a4>

    """
    
    def __init__(self,genobj,tid=None,parent=None,name=None):
        self.obj = genobj
        nice = 0
        self.ptid = None
        if parent:
            nice = parent.nice
            self.ptid = parent.tid
        self.delay = nice
        self.errpin = None
        self.name = name
        self.nice = nice
        self.priority = nice
        self.result = kernel.eagain
        self.resultReady = True
        self.sleep = 0
        self.sleepDone = 0
        self.itermode = False
        self.tid = tid
        self.time = time.time()
        self.until = None
        self.untilArgs = None

    def __repr__(self):
        return str(self.__dict__)

    # syntactic sugar to let us iterate on the task object as
    # if it were the generator object, while still allowing the
    # kernel to do the iteration and capture the results
    def XXX__iter__(self):
        self.wrapper=Wrapper(self).wrapper()
        return self.wrapper
    def XXXnext(self):
        if not hasattr(self,'wrapper'):
            self.wrapper=Wrapper(self).wrapper()
        return self.wrapper.next()
    def __iter__(self):
        if not self.itermode:
            raise Exception("set itermode=True if you want to iterate on this task")
        return self
    def next(self):
        if not kernel.isrunning(self.tid):
            raise StopIteration
        if not self.resultReady:
            return kernel.eagain
        result = self.result
        debug("task.resultReady",self.resultReady)
        self.resultReady = False
        kernel.HZ *= 10
        return result

    def isdone(self):
        if kernel.isdone(self.tid):
            return True
        return False


kernel = Kernel()
