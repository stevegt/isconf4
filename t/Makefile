lib=../lib/python
files=$(shell find $(lib) -type f -name "*.py" | grep -v GPG.py | sort)
pythons=$(shell ./pythondetect)
export PYTHONPATH=$(lib)
# export ISFS_HOME=/tmp/var/isfs

all: $(pythons)

python2.2 python2.3 python2.4 python2.5: 
	$(MAKE) run python=$@

run: mdir=metrics/$(python)
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

FORCE:
