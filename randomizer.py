import re
import random
import struct
import copy
from collections import defaultdict
from pprint import pprint

def virus_level(virus):
	if virus == 0 or virus >= 160:
		return -1
	if virus < 0x45:
		return (virus + 3) % 4
	elif virus < 0x4a:
		return 3
	else:
		return (virus + 1) % 4

def init_virus_data():
	global virus_data
	virus_data = open('virus_data.txt', 'r').read().strip()
	virus_data = map(lambda str: map(int, str.split(' ')), virus_data.split('\n'))

# TODO: Read from ROM
def init_rom_data(rom_path):
	global rom_data
	global randomized_data
	rom_data = open(rom_path, 'rb').read()
	randomized_data = list(rom_data)

def init_chip_data():
	s = 0x11530
	global chip_data
	chip_data = []

	# Load in chip ranks from file
	chip_ranks = open('chip_data.txt', 'r').read().strip()
	chip_ranks = map(int, chip_ranks.split('\n'))

	chip_names = open('chip_names.txt', 'r').read().strip()
	chip_names = chip_names.split('\n')

	chip_data.append({})
	for i in range(286):
		code1, code2, code3, code4, code5, code6, filler, regsize, chip_type, power, num = struct.unpack('<BBBBBBIBBHH', rom_data[s : s + 16])
		# chip_type seems to be a bitfield, only look at lsb for now
		is_attack = chip_type & 1
		codes = filter(lambda x : x != 255, [code1, code2, code3, code4, code5, code6])
		if num <= 200:
			rank = chip_ranks[num - 1]
		else:
			rank = 5
		if num >= 1 and num <= 200:
			name = chip_names[num - 1]
		else:
			name = ''
		chip = {
			'name' : name,
			'codes' : codes,
			'is_attack' : is_attack,
			'regsize' : regsize,
			'power' : power,
			'num' : num,
			'rank' : rank
		}
		chip_data.append(chip)
		s += 32

def write_data(str, offset):
	for i in range(len(str)):
		randomized_data[offset + i] = str[i]

def virus_replace(ind):
	# Ignore navis for now
	if ind >= 168:
		return ind
	# Also ignore coldhead, windbox, yort1 for now
	if ind in [0x16, 0x29, 0x39]:
		return ind
	old_hp, old_attack = virus_data[ind]
	if old_hp == -1:
		return ind

	candidates = []
	for i in range(len(virus_data)):
		virus_hp, virus_attack = virus_data[i]
		if virus_hp == -1:
			continue
		if virus_level(i) == virus_level(ind):
			candidates.append(i)
	return random.choice(candidates)

def randomize_viruses():
	battle_regex = re.compile('(?s)\x00[\x01-\x03][\x01-\x03]\x00(?:.[\x01-\x06][\x01-\x03].)+\xff\x00\x00\x00')

	n_battles = 0
	for match in battle_regex.finditer(rom_data):
		# Sanity check
		if match.start() >= 0x22000:
			break
		n_battles += 1
		for i in range(match.start(), match.end(), 4):
			if rom_data[i + 3] == '\x01':
				virus_ind = ord(rom_data[i])
				write_data(chr(virus_replace(virus_ind)), i)
	print 'randomized %d battles' % n_battles

def generate_chip_permutation():
	# 200 standard chips
	# 86 mega chips
	# giga chips are weird but nobody cares
	all_chips = defaultdict(list)
	for chip_ind in range(1, 287):
		chip = chip_data[chip_ind]
		chip_id = chip['rank'] + 10 * chip['is_attack']
		all_chips[chip_id].append(chip_ind)
	# Do the shuffling
	chip_map = {}
	for key, chips in all_chips.iteritems():
		keys = copy.copy(chips)
		random.shuffle(chips)
		for old_chip, new_chip in zip(keys, chips):
			chip_map[old_chip] = new_chip
	return chip_map

def randomize_folders():
	s = 0xcbdc

	n_folders = 0
	permutations = []
	while True:
		folder_start = s
		# Check if this is the end
		# There are actually 14 folders, the last 3 are for tutorial only
		# Better to just leave them alone
		if n_folders == 11:
			break
		n_folders += 1
		chip_map = generate_chip_permutation()
		permutations.append(chip_map)
		for i in range(30):
			old_chip, old_code = struct.unpack('<HH', rom_data[s:s+4])
			new_chip = chip_map[old_chip]
			# Need to determine code
			try:
				old_code_ind = chip_data[old_chip]['codes'].index(old_code)
				new_codes = chip_data[new_chip]['codes']
				new_code_ind = old_code_ind % len(new_codes)
				new_code = new_codes[new_code_ind]
			except ValueError:
				# whoops
				new_code = old_code

			chipstr = struct.pack('<HH', new_chip, new_code)
			write_data(chipstr, s)
			s += 4
	print 'randomized %d folders' % n_folders

def main(rom_path, output_path):
	random.seed()
	init_rom_data(rom_path)

	init_virus_data()
	init_chip_data()

	randomize_viruses()
	randomize_folders()

	open(output_path, 'wb').write(''.join(randomized_data))


if __name__ == '__main__':
	main('white.gba', 'white_randomized.gba')
