import re
import random
import time
import struct
import copy
from collections import defaultdict
from pprint import pprint

from rom import Rom
import enemies
import chips
import util

banned_viruses = ['Shadow', 'Twins', 'Mushy', 'Number1', 'Number2', 'Number3']
banned_chips = ['Mettaur', 'Bunny', 'Spikey', 'Swordy', 'Jelly', 'Mushy', 'Momogra', 'KillrEye', 'Scuttlst', 'Punk']

def init_rom_data(rom_path):
	global rom
	rom = Rom(rom_path)

def virus_replace(ind):
	if ind == 255:
		return ind
	# Ignore navis for now, except for invincible Bass1
	old_enemy = enemies.lookup(ind)
	if old_enemy.name == 'Bass1':
		return enemies.find(name = 'BassGS').ind
	if old_enemy.name == 'Alpha':
		return enemies.find(name = 'AlphaOmega').ind
	if old_enemy.is_navi:
		if old_enemy.level <= 0:
			return ind
		# Make the folder lock battles easier
		if old_enemy.name in ['GutsMan', 'MetalMan']:
			return enemies.find(name = old_enemy.name, level = min(4, old_enemy.level + 1)).ind
		else:
			return enemies.find(name = old_enemy.name, level = min(4, old_enemy.level + 2)).ind
		# return ind

	# Also ignore coldhead, windbox, yort1 for now
	if old_enemy.full_name in ['HardHead2', 'WindBox1', 'Yort1']:
		return ind

	candidates = []
	assert(old_enemy.is_navi is False)
	candidates = enemies.where(is_navi = False, effective_level = lambda x : x >= old_enemy.effective_level)
	candidates = filter(lambda enemy : enemy.name not in banned_viruses, candidates)
	# Special case mettaur because we want tutorial to be possible
	if old_enemy.full_name == 'Mettaur1':
		candidates = filter(lambda enemy : enemy.hp <= 100, candidates)
	return random.choice(candidates).ind

def randomize_viruses():
	battle_regex = re.compile('(?s)\x00[\x01-\x03][\x01-\x03]\x00(?:.[\x01-\x06][\x01-\x03].)+\xff\x00\x00\x00')

	n_battles = 0
	for match in battle_regex.finditer(rom.rom_data):
		# Sanity check
		if match.start() >= 0x22000:
			break
		n_battles += 1
		rom.seek(match.start())
		battle_data = list(rom.read(match.end() - match.start()))
		for i in range(0, len(battle_data), 4):
			if battle_data[i + 3] == '\x01':
				virus_ind = ord(battle_data[i])
				battle_data[i] = chr(virus_replace(virus_ind))
		rom.write(battle_data)
	print 'randomized %d battles' % n_battles

def generate_chip_permutation(allow_conditional_attacks = False, uber_random = True, recov_only = False):
	all_recov_chips = map(lambda chip : chip.ind, chips.where(name = lambda t : 'Recov' in t))
	chips_by_level = defaultdict(list)
	# Divide chips into equivalence classes
	for chip in chips.where():
		chip_id = chip.level
		if uber_random:
			if chip_id >= 10:
				chip_id = 10
			elif chip_id >= 0:
				chip_id = 0
		# Treat standard attacking chips differently from standard nonattacking chips
		if chip.is_attack and (allow_conditional_attacks or not chip.is_conditional) and chip_id < 10:
			chip_id += 1000
		# Also treat banned chips specially
		if chip.name in banned_chips:
			chip_id = chip.name
		chips_by_level[chip_id].append(chip.ind)
	# Shuffle inside each class and aggregate
	chip_map = {}
	for key, vals in chips_by_level.iteritems():
		keys = copy.copy(vals)

		random.shuffle(vals)
		for old_chip, new_chip in zip(keys, vals):
			chip_map[old_chip] = new_chip

		if recov_only:
			# Remove all non-recov chips
			t = list(set(vals).intersection(all_recov_chips))
			if t:
				for old_chip in keys:
					chip_map[old_chip] = random.choice(t)

	return chip_map

def randomize_gmds():
	for gmd_table in rom.gmd_tables:
		# Replace chip tables
		for chip_table in gmd_table.chip_tables:
			for i in range(len(chip_table)):
				old_chip, old_code = chip_table[i]
				chip_map = generate_chip_permutation()
				new_chip = chip_map[old_chip]
				new_code = random.choice(chips.lookup(new_chip).codes)
				chip_table[i] = (new_chip, new_code)

		# Multiply zenny tables
		for zenny_table in gmd_table.zenny_tables:
			for i in range(len(zenny_table)):
				zenny_table[i] = (zenny_table[i] * 3) / 2

	print 'randomized gmds'

def randomize_folders():
	rom.seek(0xcbdc)
	n_folders = 14

	# Keep track of chip permutations so we can reuse them for tutorial
	permutations = []

	# There are 14 folders, the last 3 are tutorial only
	for folder_ind in range(14):
		is_tutorial = (folder_ind >= 11)
		is_locked = (not is_tutorial and folder_ind >= 2)
		if is_tutorial:
			chip_map = permutations[0]
		elif is_locked:
			chip_map = generate_chip_permutation(recov_only = True)
		else:
			chip_map = generate_chip_permutation()
		permutations.append(chip_map)
		# Try to maintain old codes if same chip
		chip_code_map = {}
		chip_code_freq = defaultdict(int)
		for i in range(30):
			old_chip, old_code = struct.unpack('<HH', rom.read(4))
			new_chip = chip_map[old_chip]
			# Need to determine code
			if is_tutorial:
				# tutorial folder, dont change the code
				new_code = old_code
			else:
				key = (old_chip, old_code)
				if key not in chip_code_map:
					# Haven't seen this chip yet, give it a random code
					if is_locked:
						codes = chips.lookup(new_chip).codes
						if 26 in codes:
							chip_code_map[key] = 26
						else:
							r = {x: chip_code_freq[x] for x in codes}
							s = max(r.values())
							candidates = filter(lambda code : r[code] == s, codes)
							chip_code_map[key] = random.choice(candidates)
					else:
						chip_code_map[key] = random.choice(chips.lookup(new_chip).codes)
				new_code = chip_code_map[key]
				chip_code_freq[new_code] += 1

			chipstr = struct.pack('<HH', new_chip, new_code)
			rom.write(chipstr)
	print 'randomized %d folders' % n_folders

def chip_replace(old_chip, old_code):
	chip_map = generate_chip_permutation(allow_conditional_attacks = True)
	new_chip = chip_map[old_chip]
	new_code = random.choice(chips.lookup(new_chip).codes)
	return (new_chip, new_code)

def randomize_virus_drops():
	rom.seek(0x160a8)
	# Iceball M, Yoyo1 G, Wind *
	special_chips = [(25, 12), (69, 6), (143, 26)]
	for virus_ind in range(244):
		zenny_queue = []
		last_chip = None
		for i in range(28):
			if i % 14 == 0:
				last_chip = None
			offset = rom.r_offset
			reward = rom.read_halfword()
			# 0 = chip, 1 = zenny, 2 = health, 3 = should not happen (terminator)
			reward_type = reward >> 14;
			# Number from 0-6
			buster_rank = (i % 14) / 2
			new_reward = reward
			if reward_type == 0:
				# Read the chip data
				old_code = (reward >> 9) & 0x1f;
				old_chip = reward & 0x1ff;
				last_chip = (old_chip, old_code)

				# Randomize the chip
				if (old_chip, old_code) in special_chips:
					new_code = old_code
					new_chip = old_chip
				else:
					chip_map = generate_chip_permutation(allow_conditional_attacks = True)
					new_chip = chip_map[old_chip]
					new_code = random.choice(chips.lookup(new_chip).codes)
				new_reward = new_chip + (new_code << 9)

			elif reward_type == 1:
				# Only turn lvl 5+ drops to chips
				if buster_rank >= 2:
					if last_chip is None:
						# No chip yet, queue it for later
						zenny_queue.append(offset)
					else:
						old_chip, old_code = last_chip
						new_chip, new_code = chip_replace(old_chip, old_code)
						new_reward = new_chip + (new_code << 9)

			rom.write_halfword(new_reward)

			if i % 14 == 13 and last_chip is None:
				try:
					enemy = enemies.lookup(virus_ind)
					if not enemy.is_navi:
						if enemy.level == 4:
							chip = random.choice(chips.where(level = util.leq(19)))
						else:
							chip = random.choice(chips.where(level = util.leq(9)))
						last_chip = (chip.ind, random.choice(chip.codes))
				except Exception:
					# whoops
					pass

			if zenny_queue and last_chip is not None:
				old_chip, old_code = last_chip
				# Discharge the queue
				for old_offset in zenny_queue:
					new_chip, new_code = chip_replace(old_chip, old_code)
					rom.write_halfword(new_chip + (new_code << 9), old_offset)
				zenny_queue = []

	print 'randomized virus drops'

def randomize_shops():
	shop_regex = re.compile('(?s)[\x00-\x01]\x00\x00\x00...\x08...\x02.\x00\x00\x00')
	last_ind = 0
	n_shops = 0
	# white only: blue is 0x43dbc
	item_data_offset = 0x44bc8
	# item_data_offset = 0x43dbc
	first_shop = None
	for match in shop_regex.finditer(rom.rom_data):
		print match.start()
		shop_offset = match.start()
		n_shops += 1
		currency, filler, first_item, n_items = struct.unpack('<IIII', rom.read(16, shop_offset))
		if first_shop is None:
			first_shop = first_item
		# Convert RAM address to ROM address
		item_offset = first_item - first_shop + item_data_offset
		# n_items is actually an upper bound on number of items, not exact
		# Terminate if upper bound is met or on zero
		while n_items >= 0 and rom.read_dblword(item_offset) != 0:
			if rom.read_dblword(item_offset) == 0 or n_items < 0:
				break
			item_type, stock, old_chip, old_code, filler, price = struct.unpack('<BBHBBH', rom.read(8, item_offset))
			# We only care about chips
			if item_type == 2:
				chip_map = generate_chip_permutation()
				print old_chip, old_code
				new_chip = chip_map[old_chip]
				new_code = random.choice(chips.lookup(new_chip).codes)
				new_item = struct.pack('<BBHBBH', item_type, stock, new_chip, new_code, filler, price)
				rom.write(new_item, item_offset)
			item_offset += 8
			n_items -= 1

	print 'randomized %d shops' % n_shops

def randomize_number_trader():
	# 3e 45 cc 86 90 18 4f 09 61 e9
	# rom.seek(0x47928)
	rom.seek(0x47910)
	n_rewards = 0
	while True:
		reward_type, old_code, old_chip, encrypted_number = struct.unpack('<BBH8s', rom.read(12))
		if reward_type == 0xff:
			break
		if reward_type == 0:
			chip_map = generate_chip_permutation()
			new_chip = chip_map[old_chip]
			new_code = random.choice(chips.lookup(new_chip).codes)
			new_reward = struct.pack('<BBH8s', reward_type, new_code, new_chip, encrypted_number)
			rom.write(new_reward)
		n_rewards += 1
	print 'randomized %d number trader rewards' % n_rewards

def rape_mode():
	# offset = 0x2b16a
	offset = 0x2b152
	magic = 0x2164
	rom.write_halfword(magic, offset)
	print 'you are so fucked'

def main(rom_path, output_path):
	random.seed()
	init_rom_data(rom_path)

	import bn3
	bn3.load_all(rom)
	bn3.balance_chips()

	randomize_viruses()
	randomize_folders()
	randomize_virus_drops()
	# randomize_gmds()
	# randomize_shops()
	randomize_number_trader()
	rape_mode()

	bn3.write_all(rom)
	open(output_path, 'wb').write(''.join(rom.buffer))
	print 'rom created'


if __name__ == '__main__':
	main('underking.gba', 'random.gba')
