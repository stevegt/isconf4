# PREFIX=/var/is/conf
# tmpdir=/tmp/isconf-make.tmp
version=`cat version`
revision=`cat revision`
tarname=isconf-$(version).$(revision)
tarball=/tmp/$(tarname).tar.gz
pubdoc=/var/trac/isconf/pub/doc/$(version).$(revision)

all:

README.md: doc/isconf.t2t.in doc
	pandoc -o README.md doc/isconf.html 


install:
	python ./setup.py install
	# chmod might be needed with some versions of distutils
	# chmod 755 /usr/bin/isconf   


# XXX should be called by a script which does the snap and untar 
XXXupgrade: 
	isconf make install
	isconf exec chmod 755 /usr/bin/isconf
	isconf reboot
	isconf ci

start:
	/etc/init.d/isconf stop
	sleep 1
	/etc/init.d/isconf start
	sleep 5

ctags:
	# requires Exuberant ctags 
	# ctags --language-force=python bin/isconf
	cd bin; ctags --language-force=python isconf

XXXtar: 
	./update-revision
	rm -rf $(tmpdir)
	mkdir -p $(tmpdir)/$(tarname)
	cp -a . $(tmpdir)/$(tarname)
	tar -C $(tmpdir) --exclude=*.pyc --exclude=*.swp --exclude=*.swo --exclude=.coverage -czvf $(tarball) $(tarname)
	rm -rf $(tmpdir)

sdist: uprev doc
	rm -f MANIFEST
	python setup.py sdist
	mv dist/$(tarname).tar.gz $(tarball)

ship: sdist
	scp $(tarball) root@trac.t7a.org:/var/trac/isconf/pub
	ssh root@trac.t7a.org mkdir -p $(pubdoc)
	rsync -e ssh -avz doc/ root@trac.t7a.org:$(pubdoc)
	# XXX 'latest' is wrong if we're working on a patch branch
	ssh root@trac.t7a.org rsync -avz $(pubdoc)/ /var/trac/isconf/pub/doc/latest/

test:
	cd t && time make

uprev:
	./update-revision

doc: FORCE
	cd doc && make 

%:
	cd t && $(MAKE) $*

FORCE:
