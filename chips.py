# Behold the magic of copy paste
all_chips = {}

class Chip(object):
	def __init__(self, name, level):
		self.name = name
		self.level = level

		self.codes = None
		self.is_attack = None
		self.is_conditional = None
		self.regsize = None
		self.power = None
		# Library number
		self.num = None

	def __repr__(self):
		return self.name

def add_chip(ind, name, level):
	x = Chip(name, level)
	assert(ind not in all_chips)
	x.ind = ind
	all_chips[ind] = x
	return x

def lookup(ind):
	return all_chips[ind]

def where(**kwargs):
	return filter(lambda enemy : all([key in enemy.__dict__ and (val(enemy.__dict__[key]) if callable(val) else enemy.__dict__[key] == val) for key, val in kwargs.iteritems()]), all_chips.values())

def find(**kwargs):
	results = where(**kwargs)
	assert(len(results) == 1)
	return results[0]
