# vim:set expandtab:
# vim:set foldmethod=indent:
# vim:set shiftwidth=4:
# vim:set tabstop=4:

from __future__ import generators
import copy
import os
import sys
import time

from isconf.Globals import *

class Buffer:
    """
    
    >>> def gena(inpin,outpin):
    ...     i = 0
    ...     while True:
    ...         yield inpin.wait()
    ...         j = inpin.rx()
    ...         i += j
    ...         outpin.tx(i)
    ... 
    >>> def genb(inpin,outpin):
    ...     i = 0
    ...     while True:
    ...         yield inpin.wait()
    ...         j = inpin.rx()
    ...         i -= j
    ...         outpin.tx(i)
    ... 
    >>> bus1 = Buffer()
    >>> bus2 = Buffer()
    >>> bus3 = Buffer()
    >>> bus1.tx(1)
    1
    >>> bus1.rx()
    1
    >>> bus1.rx()
    'EAGAIN'
    >>> a = kernel.spawn(gena(inpin=bus1,outpin=bus2))
    >>> b = kernel.spawn(genb(inpin=bus2,outpin=bus3))
    >>> kernel.run(steps=100)
    >>> bus1.tx(5)
    1
    >>> bus2.rx()
    'EAGAIN'
    >>> bus1.data
    [5]
    >>> bus1.ready()
    1
    >>> kernel.run(steps=100)
    >>> bus1.data
    []
    >>> bus2.data
    []
    >>> bus3.data
    [-5]
    >>> bus1.tx(7)
    1
    >>> kernel.run(steps=100)
    >>> bus3.rx()
    -5
    >>> bus3.rx()
    -17
    >>> bus3.rx()
    'EAGAIN'
    
    """
    
    def __init__(self,maxlen=None):
        self.data=[]
        self.maxlen=maxlen

    def tx(self,msg):
        if self.maxlen and len(self.data) + 1 > self.maxlen:
            raise BufferOverflow
        self.data.append(msg)
        return 1  # XXX should be actual number of readers

    def ready(self,expires=None):
        if (expires is not None) and time.time() > expires:
            return True
        return len(self.data)

    def rx(self):
        if not len(self.data):
            return kernel.eagain
        return self.data.pop(0)

    def wait(self,timeout=None):
        expires = None
        if timeout is not None:
            expires = time.time() + timeout
        return kernel.siguntil, self.ready, expires

class BufferOverflow(Exception): pass

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

    sigcall='call'
    sigbusy='busy'
    signice='nice'
    sigret='ret'
    sigsleep='sleep'
    sigspawn='spawn'
    siguntil='until'
    signals = ( sigbusy, signice, sigsleep, sigspawn, siguntil )
    eagain = 'EAGAIN'

    def __init__(self):
        self._tasks = {}
        self._nextid = 1
        self.HZ = 1000

    def isrunning(self,tid):
        return self._tasks.get(tid,False)

    def kill(self,tid):
        self._tasks.setdefault(tid,None)
        del self._tasks[tid]

    def killall(self):
        self._tasks = {}

    def ps(self):
        out = ''
        for id in self._tasks.keys():
            task = self._tasks[id]
            out += str(task) + "\n"
        return out

    def spawn(self,genobj,step=False):
        """
        Let the kernel manage an ordinary generator object by wrapping
        it in a Task -- extremely powerful, because this means a yield
        in an ordinary generator will allow unrelated tasks to run.
        It also means ordinary generators can yield sig* values to
        talk to the kernel e.g. sigsleep.

        If step=False, then run freely, returning values only to the
        kernel, which is going to interpret them as control signals or
        throw them away if unrecognized.

        If step=True, then run in single-step mode and return each
        value to the caller like a normal generator.  The only unusual
        thing the caller needs to know is that if there is no result
        ready, then you will get a kernel.eagain result instead.  (And
        you'll always get eagain on the first read, to remind you to
        watch for it later.)

        >>> def mygen():
        ...     i = 0
        ...     while True:
        ...         yield i
        ...         if i == 3: yield kernel.sigsleep,1
        ...         i += 1
        ... 
        >>> obj = kernel.spawn(mygen(),step=True)
        >>> kernel.run(steps=10)
        >>> obj.next()
        'EAGAIN'
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
        >>> while obj.next() != 4:
        ...         kernel.run(steps=10)
        ... 
        >>> kernel.run(steps=100)
        >>> obj.next()
        5
        >>> kernel.run(steps=100)
        >>> obj.next()
        6
        >>> obj.step=False
        >>> kernel.run(steps=100)
        >>> assert obj.next() > 10
        
        """

        task = Task(genobj,tid=self._nextid)
        tid = task.tid
        assert tid == self._nextid
        self._nextid += 1
        self._tasks[tid] = task
        task.step = step
        return task

    def run(self, initobj=None, steps=None):
        """
        runs for {steps} or until init task is done
        
        """
        assert initobj or steps
        if initobj and not self.isrunning(1): 
            initid = self.spawn(initobj).tid
        ticks = 0
        while True:
            if initobj and not self.isrunning(initid): break
            if steps and steps <= ticks: 
                break
            ticks += 1
            # print self.HZ
            time.sleep(1/self.HZ)
            if not steps:
                self.HZ *= .9
            self.HZ = max(self.HZ,1)
            self.HZ = min(self.HZ,999999999)
            # if verbose and self.HZ < 100:
            # print "HZ", self.HZ 
            for tid in self._tasks.keys():
                task = self._tasks[tid]
                task.priority = min(task.priority, 99)
                # wait for N ticks if delay is set
                if task.delay > 1:
                    task.delay -= 1
                    continue
                task.delay += task.priority
                if task.sleep and task.sleepDone > time.time():
                    # slow down so we don't beat up time()
                    task.priority += 1
                    continue
                task.sleep = None
                # wait until condition is met
                if task.until:
                    done=False
                    if isinstance(task.untilArgs,list) or \
                           isinstance(task.untilArgs,tuple):
                        done = task.until(*task.untilArgs)
                    elif task.untilArgs:
                        done = task.until(task.untilArgs)
                    else:
                        done = task.until()
                    if not done:
                        # slow down so we don't beat up until()
                        task.priority += 1
                        continue
                task.until = None
                if task.step and task.resultReady:
                    # we're waiting for Task._wrapper() to pick up our
                    # previous result
                    task.priority += 1
                    continue
                self.step(task)

    def step(self,task,showstop=None):
        obj = task.obj
        tid = task.tid
        try:
            argv = obj.next()
        except StopIteration:
            del self._tasks[tid]
            if showstop: raise
            return
        except ValueError, e:
            if e == 'generator already executing':
                # kernel.run() is nested -- that's okay to do
                return
        # figure out why task yielded and what it wants
        targv = argv
        if not isinstance(targv,tuple):
            targv = (targv,)
        if targv:
            why = targv[0]
        if why:
            # print "why",why
            self.HZ *= 10
        sigargs = None
        if len(targv) > 1:
            sigargs = targv[1:]
        if why == self.sigbusy:
            pass
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
        elif why == self.sigcall:
            # XXX initialize all of these in Task
            self.callobj = sigargs[0]
            task.context = sigargs[1]
            task.until = task.context.done 
            cotid = self.spawn(self.callobj).tid
            cotask = self._tasks[cotid]
            cotask.caller = task
            cotask.context = task.context
        elif why == self.sigret:
            task.context.ret()
        else:
            # we got an ordinary value back -- save it for spawn()
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
    
    def __init__(self,genobj,tid=None,parent=None):
        self.obj = genobj
        nice = 0
        self.ptid = None
        if parent:
            nice = parent.nice
            self.ptid = parent.tid
        self.delay = nice
        self.nice = nice
        self.priority = nice
        self.result = kernel.eagain
        self.resultReady = True
        self.sleep = 0
        self.sleepDone = 0
        self.step = None
        self.tid = tid
        self.time = time.time()
        self.until = None
        self.untilArgs = None

    def __repr__(self):
        return str(self.__dict__)

    # syntactic sugar to let us iterate on the task object as
    # if it were the generator object, while still allowing the
    # kernel to do the iteration and capture the results
    def __iter__(self):
        self.wrapper=Wrapper(self).wrapper()
        return self.wrapper
    def next(self):
        if not hasattr(self,'wrapper'):
            self.wrapper=Wrapper(self).wrapper()
        return self.wrapper.next()

class Wrapper:

    def __init__(self,task):
        assert task.step
        self.task = task
    
    def wrapper(self):
        task = self.task
        # each time the kernel calls task.obj.next(), it will
        # store the result in task.result, and set
        # task.resultReady 
        while True:
                if not kernel.isrunning(task.tid):
                    raise StopIteration
                if not task.resultReady:
                    yield kernel.eagain
                    continue
                result = task.result
                task.resultReady = False
                kernel.HZ *= 10
                yield result

    def __del__(self):
        # XXX this does not work because task.wrapper is a
        # reference; step mode tasks are a memory
        # leak, and need to be explicitly removed with
        # kernel.kill() if they don't terminate themselves
        kernel.kill(self.task.tid)

kernel = Kernel()
