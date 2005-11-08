lib=../lib/python
files=$(shell find $(lib) -type f -name "*.py" | grep -v GPG.py | sort)
pythons=$(shell ./pythondetect)
export PYTHONPATH=$(lib)
python=python2.3
mdir=metrics/$(python)
tdir=/tmp/isconftest
# labhosts=test1 test2 test3 test4
labhosts=n4h1 n4h2 n4h3 n4h4
COVERAGE=

all: unittest 
	
unittest: $(pythons)

XXXsystest: python2.2 labtest
	./fetch-coverage $(labhosts)
	python2.2 ./coverage.py -r $(files) 2>&1 | tee metrics/systest/coverage.txt
	python2.2 ./coverage.py -rm $(files) 2>&1 | tee metrics/systest/missing.txt

python2.3 python2.4 python2.5: 
	$(MAKE) run python=$@

run:
	# - killall isconf
	$(python) ./coverage.py -e
	$(python) ./coverage.py -x rundoctest.py 2>&1 \
		| egrep '^ *[0-9]+' | grep -v 'had no tests' \
		|  tee $(mdir)/doctest.txt
	# COVERAGE="$(python) ./coverage.py -x" $(python) runsystest.py 2>&1 | tee $(mdir)/systest.txt 
	$(python) ./coverage.py -r $(files) 2>&1 | tee $(mdir)/coverage.txt
	$(python) ./coverage.py -rm $(files) 2>&1 | tee $(mdir)/missing.txt
	# - killall isconf

%.py: FORCE
	python $@

umlsync:
	cd .. && rsync -PHaSvuz --exclude=*.pyc . root@isconf10:/tmp/isconftest
	cd .. && rsync -PHaSvuz --exclude=*.pyc . root@isconf11:/tmp/isconftest
	cd .. && rsync -PHaSvuz --exclude=*.pyc . root@isconf12:/tmp/isconftest
	cd .. && rsync -PHaSvuz --exclude=*.pyc . root@isconf13:/tmp/isconftest

umltest: umlsync
	time python2.3 runlabtest.py /tmp/isconftest \
		isconf10 isconf11 isconf12 isconf13

labsync:
	rm -f ../.coverage
	$(MAKE) -j 4 $(labhosts)

$(labhosts):
	cd .. && rsync -PHaSvuz --delete --exclude=*.pyc . root@$@:$(tdir)

coverage: COVERAGE=1
coverage: python2.3 labtest
	./fetch-coverage $(labhosts)
	python2.3 ./coverage.py -r $(files) 2>&1 | tee metrics/systest/coverage.txt
	python2.3 ./coverage.py -rm $(files) 2>&1 | tee metrics/systest/missing.txt

labtest: labsync
	COVERAGE=$(COVERAGE) time python2.3 runlabtest.py /tmp/isconftest \
		$(labhosts) 
	mv runlabtest.log metrics/systest/systest.txt 

tarsync:
	t/tarsync $(tarname) test1 test2 test3

tartest: tarsync
	time python2.3 t/runlabtest.py /tmp/$(tarname) \
		test1 test2 test3

mtatest:
	- killall isconf
	- bin/isconf -v selftest -p
	sleep 5
	# GNUPGHOME=/tmp/`ls -rt /tmp | tail -1`/foo/.gnupg; cd mta; make
	# export GNUPGHOME=`ls -rtd /tmp/[0-9]*/A/.gnupg | tail -1`; \
	export GNUPGHOME=/tmp/isconf-test/A/var/is/.gnupg; $(MAKE) -C mta all

FORCE:
