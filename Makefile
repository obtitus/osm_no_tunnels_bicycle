cover_packages="--cover-package=."

test:
	nosetests --with-doctest . -v \
		--with-coverage --cover-inclusive --cover-erase --cover-package=. --cover-tests --cover-html

# fixme:
#--with-profile --profile-stats-file=cover/profile.stats

doctest:
	python -m doctest -v *.py

unittest:
	python -m unittest discover
