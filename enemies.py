all_enemies = []
banned_enemies = []

class Enemy(object):
	def __init__(self, name, level):
		self.name = name
		self.level = level
		self.effective_level = self.get_effective_level()
		self.full_name = self.get_full_name()

		self.hp = None
		self.attack = None
		self.is_navi = None

	def get_effective_level(self):
		level = self.level
		if self.name in ['Mettaur', 'Canodumb', 'Bunny']:
			level = max(level - 1, 0)
		return level

	def get_full_name(self):
		if self.level <= 0:
			return self.name
		levels = ['1', '2', '3', 'Omega']
		return self.name + levels[self.level - 1]

	def __repr__(self):
		return self.full_name

def add_enemy(name, level):
	x = Enemy(name, level)
	x.ind = len(all_enemies)
	all_enemies.append(x)
	return x

def lookup(ind):
	return all_enemies[ind]

# like sql
def where(candidates = all_enemies, **kwargs):
	return filter(lambda enemy : all([key in enemy.__dict__ and (val(enemy.__dict__[key]) if callable(val) else enemy.__dict__[key] == val) for key, val in kwargs.iteritems()]), candidates)
