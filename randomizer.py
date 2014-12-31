import re
import random
import time
import struct
import copy
from collections import defaultdict
from pprint import pprint

from rom import Rom
import enemies

N_CHIPS = 312
banned_viruses = ['Shadow', 'Twins', 'Mushy', 'Number1', 'Number2', 'Number3']
banned_chips = [0x110]

def virus_level(virus):
	if virus == 0 or virus >= 0x9f:
		return -1
	if virus in special_virus_level:
		return special_virus_level[virus]
	if virus < 0x45:
		return (virus + 3) % 4
	elif virus < 0x4a:
		return 3
	else:
		return (virus + 1) % 4

def init_rom_data(rom_path):
	global rom
	rom = Rom(rom_path)

def init_chip_data():
	rom.seek(0x11530)
	global chip_data
	chip_data = []

	# Load in chip ranks from file
	chip_ranks = open('chip_data.txt', 'r').read().strip()
	chip_ranks = map(int, chip_ranks.split('\n'))

	chip_names = open('chip_names.txt', 'r').read().strip()
	chip_names = chip_names.split('\n')

	chip_data.append({})
	for i in range(N_CHIPS):
		code1, code2, code3, code4, code5, code6, filler, regsize, chip_type, power, num, more_filler = struct.unpack('<BBBBBBIBBHH16s', rom.read(32))
		# chip_type seems to be a bitfield, only look at lsb for now
		is_attack = (chip_type & 1)
		codes = filter(lambda x : x != 255, [code1, code2, code3, code4, code5, code6])

		if num <= 200:
			rank = chip_ranks[num - 1]
		else:
			rank = chip_ranks[i]

		if num >= 1 and num <= 200:
			name = chip_names[num - 1]
		else:
			name = chip_names[i]

		if name == 'VarSwrd':
			power = 60
			rom.write_byte(power, rom.r_offset - 32 + 12)

		# Conditional attacks
		is_conditional = name in ['Spice1', 'Spice2', 'Spice3', 'BlkBomb1', 'BlkBomb2', 'BlkBomb3', 'GrabBack', 'GrabRvng', 'Snake', 'Team1', 'Slasher', 'NoBeam1', 'NoBeam2', 'NoBeam3']

		chip = {
			'name' : name,
			'codes' : codes,
			'is_attack' : bool(is_attack),
			'is_conditional' : is_conditional,
			'regsize' : regsize,
			'power' : power,
			'num' : num,
			'rank' : rank,
		}

		chip_data.append(chip)

def randomize_gmds():
	# does not work in blue!
	base_offset = 0x28810
	free_space_offset = 0x67c000
	map_data = {
		0x10: [0, 1, 2],
		0x11: [0, 1],
		0x12: [0, 1],
		0x13: [0, 1, 3],
		0x14: [0, 1, 2, 3, 4, 5, 6],
		0x15: [0, 1, 2]
	}
	new_scripts = {}
	area = 0x10
	subarea = 0x0
	chip_regex = re.compile('(?s)\xf1\x00\xfb\x04\x0f(.{32})')
	zenny_regex = re.compile('(?s)\xf1\x00\xfb\x00\x0f(.{64})')
	earliest_script = 999999999
	end_addr = -1
	for area, subareas in map_data.iteritems():
		for subarea in subareas:
			script_ptr = rom.read_word(base_offset + 4 * area) - 0x08000000 + 4 * subarea
			earliest_script = min(earliest_script, script_ptr)
			script_addr = rom.read_word(script_ptr) - 0x08000000
			script_data = rom.read_lz77(script_addr)
			end_addr = max(end_addr, rom.lz77_end)
			new_data = map(ord, script_data)

			# Replace chip tables
			for match in chip_regex.finditer(script_data):
				match_offset = match.start() + 5
				x = map(lambda x : ord(x), list(match.groups()[0]))
				for i in range(0, len(x), 2):
					chip_map = generate_chip_permutation()
					old_chip = x[i]
					new_chip = chip_map[old_chip]
					new_code = random.choice(chip_data[new_chip]['codes'])
					new_data[match_offset + i] = new_chip
					new_data[match_offset + i+1] = new_code

			# Multiply zenny tables
			for match in zenny_regex.finditer(script_data):
				match_offset = match.start() + 5
				zennys = list(struct.unpack('<IIIIIIIIIIIIIIII', match.groups()[0]))
				for i in range(16):
					zennys[i] = (zennys[i] * 3) / 2
				zenny_str = struct.pack('<IIIIIIIIIIIIIIII', *zennys)
				for i in range(len(zenny_str)):
					new_data[match_offset + i] = ord(zenny_str[i])

			new_script = ''.join(map(chr, new_data))
			new_scripts[script_ptr] = rom.lz77_compress(new_script)

	# Get the missing scripts that were not edited
	rom.seek(earliest_script)
	while True:
		offset = rom.r_offset
		script_addr = rom.read_word()
		if script_addr == 0:
			break
		if offset not in new_scripts:
			script_addr -= 0x08000000
			script_data = rom.lz77_compress(rom.read_lz77(script_addr))
			new_scripts[offset] = script_data

	script_offset = rom.read_word(earliest_script) - 0x08000000
	# Write all the scripts back
	n_full_writes = 0
	for script_ptr, script_data in new_scripts.iteritems():
		# Check if there is space for this script in the script memory region
		if script_offset + len(script_data) < end_addr:
			rom.write(script_data, script_offset)
			rom.write_word(script_offset + 0x08000000, script_ptr)
			script_offset += len(script_data)
			# Pad up to multiple of 4
			script_offset += (4 - script_offset) % 4
		else:
			# No space here, write it somewhere else
			n_full_writes += 1
			rom.write(script_data, free_space_offset)
			rom.write_word(free_space_offset + 0x08000000, script_ptr)
			free_space_offset += len(script_data)
			# Pad up to multiple of 4
			free_space_offset += (4 - free_space_offset) % 4
	# Quick sanity check
	assert(n_full_writes <= 1)
	print 'randomized gmds'

def virus_replace(ind):
	# Ignore navis for now, except for invincible Bass1
	old_enemy = enemies.lookup(ind)
	if old_enemy.name == 'Bass1':
		return enemies.where(name = 'BassGS')[0].ind
	if old_enemy.is_navi:
		return ind

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

def generate_chip_permutation(allow_conditional_attacks = False, uber_random = True):
	all_chips = defaultdict(list)
	for chip_ind in range(1, N_CHIPS + 1):
		chip = chip_data[chip_ind]
		chip_id = chip['rank']
		if uber_random:
			if chip_id >= 10:
				chip_id = 10
			elif chip_id >= 0:
				chip_id = 0
		# Treat standard attacking chips differently from standard nonattacking chips
		if chip['is_attack'] and (allow_conditional_attacks or not chip['is_conditional']) and chip_id < 10:
			chip_id += 1000
		all_chips[chip_id].append(chip_ind)
	# Do the shuffling
	chip_map = {}
	for key, chips in all_chips.iteritems():
		keys = copy.copy(chips)
		random.shuffle(chips)
		for old_chip, new_chip in zip(keys, chips):
			chip_map[old_chip] = new_chip
	# print chip_map[1]
	# raw_input()
	return chip_map

def get_new_code(old_chip, old_code, new_chip):
	if old_code == 26 and old_code in chip_data[new_chip]['codes']:
		return old_code
	try:
		old_code_ind = chip_data[old_chip]['codes'].index(old_code)
		new_codes = chip_data[new_chip]['codes']
		new_code_ind = old_code_ind % len(new_codes)
		return new_codes[new_code_ind]
	except ValueError:
		return old_code

def randomize_folders():
	rom.seek(0xcbdc)
	n_folders = 14

	# Keep track of chip permutations so we can reuse them for tutorial
	permutations = []
	# There are 14 folders, the last 3 are tutorial only
	for folder_ind in range(14):
		is_tutorial = (folder_ind >= 11)
		if is_tutorial:
			chip_map = permutations[0]
		else:
			chip_map = generate_chip_permutation()
		permutations.append(chip_map)
		for i in range(30):
			old_chip, old_code = struct.unpack('<HH', rom.read(4))
			new_chip = chip_map[old_chip]
			# Need to determine code
			if is_tutorial:
				# tutorial folder, dont change the code
				new_code = old_code
			else:
				new_code = get_new_code(old_chip, old_code, new_chip)

			chipstr = struct.pack('<HH', new_chip, new_code)
			rom.write(chipstr)
	print 'randomized %d folders' % n_folders

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
					new_code = get_new_code(old_chip, old_code, new_chip)
				new_reward = new_chip + (new_code << 9)
				rom.write_halfword(new_reward)

				# Discharge the queue
				for old_offset in zenny_queue:
					chip_map = generate_chip_permutation(allow_conditional_attacks = True)
					new_chip = chip_map[old_chip]
					new_code = get_new_code(old_chip, old_code, new_chip)
					rom.write_halfword(new_chip + (new_code << 9), old_offset)
				zenny_queue = []

			elif reward_type == 1:
				# Only turn lvl 5+ drops to chips
				if buster_rank >= 2:
					if last_chip is None:
						# No chip yet, queue it for later
						zenny_queue.append(offset)
					else:
						old_chip, old_code = last_chip
						chip_map = generate_chip_permutation(allow_conditional_attacks = True)
						new_chip = chip_map[old_chip]
						new_code = get_new_code(old_chip, old_code, new_chip)
						new_reward = new_chip + (new_code << 9)
						rom.write_halfword(new_reward)
	print 'randomized virus drops'

def randomize_shops():
	shop_regex = re.compile('(?s)[\x00-\x01]\x00\x00\x00...\x08...\x02.\x00\x00\x00')
	last_ind = 0
	n_shops = 0
	# white only: blue is 0x43dbc
	item_data_offset = 0x44bc8
	first_shop = None
	for match in shop_regex.finditer(rom.rom_data):
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
				new_chip = chip_map[old_chip]
				new_code = random.choice(chip_data[new_chip]['codes'])
				new_item = struct.pack('<BBHBBH', item_type, stock, new_chip, new_code, filler, price)
				rom.write(new_item, item_offset)
			item_offset += 8
			n_items -= 1

	print 'randomized %d shops' % n_shops

def randomize_number_trader():
	# 3e 45 cc 86 90 18 4f 09 61 e9
	rom.seek(0x47928)
	n_rewards = 0
	while True:
		reward_type, old_code, old_chip, encrypted_number = struct.unpack('<BBH8s', rom.read(12))
		if reward_type == 0xff:
			break
		if reward_type == 0:
			chip_map = generate_chip_permutation()
			new_chip = chip_map[old_chip]
			new_code = get_new_code(old_chip, old_code, new_chip)
			new_reward = struct.pack('<BBH8s', reward_type, new_code, new_chip, encrypted_number)
			rom.write(new_reward)
		n_rewards += 1
	print 'randomized %d number trader rewards' % n_rewards

def rape_mode():
	offset = 0x2b16a
	magic = 0x2164
	rom.write_halfword(magic, offset)
	print 'you are so fucked'

def main(rom_path, output_path):
	random.seed()
	init_rom_data(rom_path)

	init_chip_data()
	import bn3
	bn3.load_enemies(rom)

	randomize_viruses()
	randomize_folders()
	randomize_virus_drops()
	randomize_gmds()
	randomize_shops()
	randomize_number_trader()
	rape_mode()

	open(output_path, 'wb').write(''.join(rom.buffer))


if __name__ == '__main__':
	main('white.gba', 'random.gba')
