import re
import random
import struct
import copy
from collections import defaultdict
from pprint import pprint

N_CHIPS = 312
# Shadows, Twinners
banned_viruses = [0x3d, 0x3e, 0x3f, 0x97, 0x98, 0x99, 0x9a]

special_virus_level = {
	0x2: 0,
	0x5f: 1,
	0x87: 1
}

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

def read_byte(offset):
	return ord(rom_data[offset])
def read_halfword(offset):
	return struct.unpack('<H', rom_data[offset:offset+2])[0]
def read_word(offset):
	return struct.unpack('<I', rom_data[offset:offset+4])[0]

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
	for i in range(N_CHIPS):
		code1, code2, code3, code4, code5, code6, filler, regsize, chip_type, power, num = struct.unpack('<BBBBBBIBBHH', rom_data[s : s + 16])
		# chip_type seems to be a bitfield, only look at lsb for now
		is_attack = (chip_type & 1)
		codes = filter(lambda x : x != 255, [code1, code2, code3, code4, code5, code6])
		if num <= 200:
			rank = chip_ranks[num - 1]
		elif num <= 286:
			rank = 5

		if num >= 1 and num <= 200:
			name = chip_names[num - 1]
		else:
			name = ''

		if name == 'VarSwrd':
			power = 60
			write_data(chr(60), s + 12)

		# Conditional attacks
		is_conditional = name in ['Spice1', 'Spice2', 'Spice3', 'BlkBomb1', 'BlkBomb2', 'BlkBomb3', 'GrabBack', 'GrabRvng', 'Snake', 'Team1', 'Slasher', 'NoBeam1', 'NoBeam2', 'NoBeam3']

		chip = {
			'name' : name,
			'codes' : codes,
			'is_attack' : is_attack,
			'is_conditional' : int(is_conditional),
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

def decompress_data(offset):
	global compressed_data_end
	decompressed_size = read_word(offset) >> 8;
	offset += 4
	output = []
	while len(output) < decompressed_size:
		flags = read_byte(offset)
		offset += 1
		for i in range(8):
			is_special = bool(flags & 0x80)
			if is_special:
				a = read_byte(offset)
				b = read_byte(offset+1)
				x_len = (a >> 4) + 3
				x_offset = (b + ((a & 0xf) << 8))
				start = len(output) - 1 - x_offset
				for j in range(x_len):
					output.append(output[start + j])
				offset += 2
			else:
				output.append(read_byte(offset))
				offset += 1
			flags <<= 1;
	output = output[:decompressed_size]
	compressed_data_end = offset
	return ''.join(map(lambda x : chr(x), output))

def compress_data(raw_data):
	ops = []
	i = 0
	data_len = len(raw_data)
	while i < data_len:
		lo = 2
		hi = min(18, len(raw_data) - i)
		start = max(0, i - 4096)
		last_match_ind = -1
		while lo < hi:
			mid = (lo + hi + 1) / 2
			ss = raw_data[i : i + mid]
			t = raw_data.find(ss, start)
			if t < i:
				# match found
				last_match_ind = t
				lo = mid
			else:
				hi = mid - 1
		if lo < 3:
			ops.append((0, ord(raw_data[i])))
			i += 1
		else:
			ops.append((i - last_match_ind, lo))
			i += lo
	# Add some padding
	n_padding = (8 - (len(ops) % 8)) % 8
	for i in range(n_padding):
		ops.append((0, 0))
	# Encode the string
	output = [0x10, data_len & 0xff, (data_len >> 8) & 0xff, (data_len >> 16) & 0xff]
	for i in range(0, len(ops), 8):
		flags = 0
		for j in range(8):
			flags <<= 1
			if ops[i + j][0] > 0:
				flags |= 1
		output.append(flags)
		for j in range(8):
			if ops[i + j][0] == 0:
				output.append(ops[i + j][1])
			else:
				o, l = ops[i + j]
				o -= 1
				l -= 3
				output.append( ((l & 0xf) << 4) + ((o >> 8) & 0xf) )
				output.append(o & 0xff)
	return ''.join(map(chr, output))

def randomize_gmds():
	base_offset = 0x28810
	free_space = 0x67c000
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
			script_ptr = read_word(base_offset + 4 * area) - 0x08000000 + 4 * subarea
			earliest_script = min(earliest_script, script_ptr)
			script_addr = read_word(script_ptr) - 0x08000000
			script_data = decompress_data(script_addr)
			end_addr = max(end_addr, compressed_data_end)
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

			# Double zenny tables
			for match in zenny_regex.finditer(script_data):
				match_offset = match.start() + 5
				zennys = list(struct.unpack('<IIIIIIIIIIIIIIII', match.groups()[0]))
				for i in range(16):
					zennys[i] *= 2
				zenny_str = struct.pack('<IIIIIIIIIIIIIIII', *zennys)
				for i in range(len(zenny_str)):
					new_data[match_offset + i] = ord(zenny_str[i])


			new_script = ''.join(map(chr, new_data))
			new_scripts[script_ptr] = compress_data(new_script)

	# Get the missing scripts
	script_ptr = earliest_script
	while True:
		script_addr = read_word(script_ptr)
		if script_addr == 0:
			break
		if script_ptr not in new_scripts:
			script_addr -= 0x08000000
			script_data = compress_data(decompress_data(script_addr))
			new_scripts[script_ptr] = script_data
		script_ptr += 4

	start_addr = read_word(earliest_script) - 0x08000000
	# Write all the scripts back
	for script_ptr, script_data in new_scripts.iteritems():
		if start_addr + len(script_data) < end_addr:
			write_data(script_data, start_addr)
			write_data(struct.pack('<I', start_addr + 0x08000000), script_ptr)
			start_addr += len(script_data)
			# Pad up to multiple of 4
			start_addr += (4 - start_addr) % 4
		else:
			write_data(script_data, free_space)
			write_data(struct.pack('<I', free_space + 0x08000000), script_ptr)
			free_space += len(script_data)
			# Pad up to multiple of 4
			free_space += (4 - free_space) % 4
	print 'randomized gmds'

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
		# Special case the mettaur because of tutorial
		if ind == 1 and virus_hp > 100:
			continue
		if virus_level(i) == virus_level(ind) and i not in banned_viruses:
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

def generate_chip_permutation(allow_conditional_attacks = False):
	# 200 standard chips
	# 86 mega chips
	# giga chips are weird but nobody cares
	all_chips = defaultdict(list)
	for chip_ind in range(1, N_CHIPS + 1):
		chip = chip_data[chip_ind]
		if allow_conditional_attacks:
			is_attack = chip['is_attack']
		else:
			is_attack = (chip['is_attack'] & (1 - chip['is_conditional']))
		chip_id = chip['rank'] + 10 * is_attack
		all_chips[chip_id].append(chip_ind)
	# Do the shuffling
	chip_map = {}
	for key, chips in all_chips.iteritems():
		keys = copy.copy(chips)
		random.shuffle(chips)
		for old_chip, new_chip in zip(keys, chips):
			chip_map[old_chip] = new_chip
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
	s = 0xcbdc

	n_folders = 0
	permutations = []
	while True:
		if n_folders == 14:
			break
		folder_start = s
		# There are 14 folders, the last 3 are tutorial only
		n_folders += 1
		is_tutorial = (n_folders >= 12 and n_folders <= 14)
		if is_tutorial:
			chip_map = permutations[0]
		else:
			chip_map = generate_chip_permutation()
		permutations.append(chip_map)
		for i in range(30):
			old_chip, old_code = struct.unpack('<HH', rom_data[s:s+4])
			new_chip = chip_map[old_chip]
			# Need to determine code
			if is_tutorial:
				# tutorial folder, dont change the code
				new_code = old_code
			else:
				new_code = get_new_code(old_chip, old_code, new_chip)

			chipstr = struct.pack('<HH', new_chip, new_code)
			write_data(chipstr, s)
			s += 4
	print 'randomized %d folders' % n_folders

def randomize_virus_drops():
	offset = 0x160a8
	# Iceball M, Yoyo1 G, Wind *
	special_chips = [(25, 12), (69, 6), (143, 26)]
	for virus_ind in range(244):
		for i in range(28):
			reward = struct.unpack('<H', rom_data[offset:offset+2])[0]
			reward_type = reward >> 14;
			# 0 = chip, 1 = zenny, 2 = health, 3 = should not happen (terminator)
			if reward_type == 0:
				old_code = (reward >> 9) & 0x1f;
				old_chip = reward & 0x1ff;

				if (old_chip, old_code) in special_chips:
					new_code = old_code
					new_chip = old_chip
				else:
					chip_map = generate_chip_permutation(allow_conditional_attacks = True)
					new_chip = chip_map[old_chip]
					new_code = get_new_code(old_chip, old_code, new_chip)

				new_reward = new_chip + (new_code << 9)
				write_data(struct.pack('<H', new_reward), offset)
			elif reward_type == 1:
				if random.random() < 0.5:
					new_chip = random.randint(1, 200)
			offset += 2
	print 'randomized virus drops'

def main(rom_path, output_path):
	random.seed()
	init_rom_data(rom_path)

	init_virus_data()
	init_chip_data()

	randomize_viruses()
	randomize_folders()
	randomize_virus_drops()
	randomize_gmds()

	open(output_path, 'wb').write(''.join(randomized_data))


if __name__ == '__main__':
	main('white.gba', 'white_randomized.gba')
