lib=../lib/python
files=$(shell find $(lib) -type f -name "*.py" | sort)
export PYTHONPATH=$(lib)

all: python2.2 python2.3

python2.2: python=python2.2
python2.2: run2.2

python2.3: python=python2.3
python2.3: run2.3

run%: mdir=metrics/$(python)
run%:
	$(python) ./coverage.py -e
	$(python) ./coverage.py -x rundoctest.py 2>&1 \
		| egrep '^ *[0-9]+' | grep -v 'had no tests' \
		|  tee $(mdir)/doctest.txt
	$(python) ./coverage.py -x runsystest.py 2>&1 | tee $(mdir)/systest.txt 
	$(python) ./coverage.py -r $(files) 2>&1 | tee $(mdir)/coverage.txt
	$(python) ./coverage.py -rm $(files) 2>&1 | tee $(mdir)/missing.txt
	test -s $(mdir)/doctest.txt || echo All unit tests pass. > $(mdir)/doctest.txt

%.py: FORCE
	python $@

FORCE:
