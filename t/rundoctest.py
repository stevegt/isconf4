
# import coverage
import doctest
import os
import re
import sys
import unittest

libpath = "../lib/python"
sys.path.append(libpath)

def main():
    # coverage.erase()
    # coverage.start()

    # prodfiles = []
    # for dir,subdirs,files in os.walk(libpath):
    #     pyfiles = filter(re.compile("^.*\.py$").search, files)
    #     prodfiles += map(lambda f: os.path.join(dir, f), pyfiles)
    # print prodfiles

    result = docTest()

    # coverage.stop()
    # for f in prodfiles:
    #     coverage.analysis(f)
    # coverage.report(prodfiles)

    sys.exit(result)

def docTest():
    modules = []
    olddir = os.getcwd()
    os.chdir(libpath)
    os.path.walk('.',getmods,modules)
    os.chdir(olddir)
    # print modules
    
    fail=0
    total=0
    imported = []
    for modname in modules:
        # XXX not enough entropy during test -- bug #20
        if modname in ('isconf.GPG','isconf.Globals'):
            continue
        # aarg!  need to include fromlist when importing from package
        # -- see pydoc
        fromlist = list('.'.join(modname.split('.')[1:]))
        imp = __import__(modname,globals(),locals(),fromlist)
        imported.append(imp)
    # print imported
    for mod in imported:
        (f,t) = doctest.testmod(mod,report=0)
        fail += f
        total += t
    doctest.master.summarize(verbose=1)
    return fail

def getmods(modules,dirname,names):
    dirname = dirname.replace("./","")
    dirname = dirname.lstrip(".")
    dirpath = dirname.split('/')
    if not dirpath[0]: dirpath.pop(0)
    for name in names:
        path = dirpath[:]
        if re.match("__",name): 
            continue
        m = re.match("(.*)\.py$",name)
        if not m:
            continue
        name = m.group(1)
        path.append(name)
        pathname = '.'.join(path)
        # print pathname
        # mod = eval(pathname)
        modules.append(pathname)

if __name__ == "__main__":
    main()

