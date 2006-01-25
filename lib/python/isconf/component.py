import sys
import os
import pickle
import types
import traceback
from subprocess import *


class component(Popen):
    """like subprocess.Popen, but runs local code after fork; does not exec

    def foo(x): 
        print x, "from foo"

    c = component([foo,'bar'], stdout=PIPE)
    c.wait()
    c.stdout.read()
    c.returncode


    """
    
    # cheating - this should really be set in __init__()
    exception = None
    traceback = None
    e = None

    def _execute_child(self, args, executable, preexec_fn, close_fds,
                       cwd, env, universal_newlines,
                       startupinfo, creationflags, shell,
                       p2cread, p2cwrite,
                       c2pread, c2pwrite,
                       errread, errwrite):
        """Execute program (derived from subprocess POSIX version)"""


        if isinstance(args, types.StringTypes):
            raise ValueError("string args unsupported")

        if not isinstance(args, list):
            args = [args]
        args = args[:]
        func = args.pop(0)

        if shell:
            raise ValueError("shell unsupported -- use subprocess")

        if executable:
            raise ValueError("executable unsupported -- use subprocess")

        if env:
            raise ValueError("env unsupported")

        # For transferring possible exec failure from child to parent
        # The first char specifies the exception type: 0 means
        # OSError, 1 means some other error.
        errpipe_read, errpipe_write = os.pipe()
        self._set_cloexec_flag(errpipe_write)

        self.pid = os.fork()
        if self.pid == 0:
            # Child
            try:
                # Close parent's pipe ends
                if p2cwrite:
                    os.close(p2cwrite)
                if c2pread:
                    os.close(c2pread)
                if errread:
                    os.close(errread)
                os.close(errpipe_read)

                # Dup fds for child
                if p2cread:
                    os.dup2(p2cread, 0)
                if c2pwrite:
                    os.dup2(c2pwrite, 1)
                if errwrite:
                    os.dup2(errwrite, 2)

                # Close pipe fds.  Make sure we doesn't close the same
                # fd more than once.
                if p2cread:
                    os.close(p2cread)
                if c2pwrite and c2pwrite not in (p2cread,):
                    os.close(c2pwrite)
                if errwrite and errwrite not in (p2cread, c2pwrite):
                    os.close(errwrite)

                # Close all other fds, if asked for
                if close_fds:
                    self._close_fds(but=errpipe_write)

                if cwd != None:
                    os.chdir(cwd)

                if preexec_fn:
                    apply(preexec_fn)

                func(*args)

            except:
                exc_type, exc_value, tb = sys.exc_info()
                # Save the traceback and attach it to the exception object
                exc_lines = traceback.format_exception(exc_type,
                                                       exc_value,
                                                       tb)
                os.write(errpipe_write,
                        pickle.dumps((exc_type,exc_value,exc_lines)))
                sys.exit(255)

            #os._exit(0)
            sys.exit(0)

        # Parent
        os.close(errpipe_write)
        if p2cread and p2cwrite:
            os.close(p2cread)
        if c2pwrite and c2pread:
            os.close(c2pwrite)
        if errwrite and errread:
            os.close(errwrite)
        self.errpipe_read = errpipe_read


    def _handle_exitstatus(self, sts):
        super(component,self)._handle_exitstatus(sts)
        # Wait for apply to fail or succeed; we only get here after
        # the child has already exited
        data = os.read(self.errpipe_read, 1048576) # Exceptions limited to 1 MB
        os.close(self.errpipe_read)
        if data != "":
            try:
                (self.exception,self.e,exc_lines) = pickle.loads(data)
            except:
                self.exception = Exception("garbled pickle")
                self.e = None
                exc_lines = ()
            self.traceback = ''.join(exc_lines)


if __name__ == '__main__':
    import time
    import sys

    def foo(x):
        open("/tmp/out",'w').write(repr(sys.stdout))
        time.sleep(3)
        print x, "from foo"
        alksjfldsa.sadf()
        raise "lasjdflkas"
        # sys.stdout.flush()
        # sys.stdout.write("baz")
        # sys.stdout.close()

    c = component([foo,'bar'],stdout=PIPE)
    while c.poll() is None:
        time.sleep(1)
        print "polling"

    print c.stdout.read()
    print c.returncode
    print c.exception
    print "e:", c.e
    print "traceback:"
    print c.traceback




"""
# Sean is ill

package foo;
use Parent1;
use Parent2;
@ISA=('Parent1','Parent2')

sub new
{
    my $class = shift;
    my $arg1 = shift;
    my $arg2 = shift;
    my $self = {};
    bless($self,$class);
}

sub bar
{
    my ($self,$arg) = @_;
    $self->SUPER::bar($arg);
}


"""

