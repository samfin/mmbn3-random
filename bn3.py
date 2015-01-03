import copy
import struct
import re

import enemies
import chips

def load_enemies(rom):
	virus_data = open('virus_data.txt', 'r').read().strip()
	virus_data = map(lambda str: str.split(' '), virus_data.split('\n'))
	# 0-indexed enemy is a blank
	ind = 0
	for enemy in virus_data:
		ind += 1
		name = enemy[0]
		level = int(enemy[1])
		if level < 0:
			continue

		x = enemies.add_enemy(ind, name, level)

		if len(enemy) >= 3:
			x.hp = int(enemy[2])
		if len(enemy) >= 4:
			x.attack = int(enemy[3])
		x.is_navi = (x.ind >= 0xa8)

conditional_chips =  ['Spice1', 'Spice2', 'Spice3', 'BlkBomb1', 'BlkBomb2', 'BlkBomb3', 'GrabBack', 'GrabRvng', 'Snake', 'Team1', 'Slasher', 'NoBeam1', 'NoBeam2', 'NoBeam3']
def load_chips(rom):
	chip_data = open('chip_data.txt', 'r').read().strip()
	chip_data = map(lambda s: s.split(' '), chip_data.split('\n'))

	# TODO: Check if white or blue
	rom.seek(0x11530)
	N_CHIPS = 312
	for i in range(N_CHIPS):
		name = chip_data[i][0]
		level = int(chip_data[i][1])
		chip = chips.add_chip(i+1, name, level)

		chip_offset = rom.r_offset
		code1, code2, code3, code4, code5, code6, filler, regsize, chip_type, power, num, more_filler = struct.unpack('<BBBBBBIBBHH16s', rom.read(32))
		chip.num = num
		chip.regsize = regsize
		# chip_type seems to be a bitfield, only look at lsb for now
		chip.is_attack = bool(chip_type & 1)
		chip.codes = filter(lambda x : x != 255, [code1, code2, code3, code4, code5, code6])
		chip.power = power

		# Conditional attacks
		chip.is_conditional = name in conditional_chips

		# Store the rest of data so we can write it later
		chip.filler = filler
		chip.chip_type = chip_type
		chip.more_filler = more_filler
		chip.offset = chip_offset

def balance_chips():
	varswrd = chips.find(name = 'VarSwrd')
	varswrd.power = 60

def write_chips(rom):
	for chip in chips.where():
		codes = copy.copy(chip.codes)
		while len(codes) < 6:
			codes.append(255)
		code1, code2, code3, code4, code5, code6 = codes
		chipstr = struct.pack('<BBBBBBIBBHH16s', code1, code2, code3, code4, code5, code6, chip.filler, chip.regsize, chip.chip_type, chip.power, chip.num, chip.more_filler)
		rom.write(chipstr, chip.offset)

def load_gmds(rom):
	gmd_tables = []

	# TODO: get offsets for blue!
	base_offset = 0x28810
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

	class GMDTable: pass

	for area, subareas in map_data.iteritems():
		for subarea in subareas:
			# Extract the key components of the script
			zenny_tables = []
			zenny_offsets = []
			chip_tables = []
			chip_offsets = []

			script_ptr = rom.read_word(base_offset + 4 * area) - 0x08000000 + 4 * subarea
			script_addr = rom.read_word(script_ptr) - 0x08000000
			script_data = rom.read_lz77(script_addr)

			# Find chip tables
			for match in chip_regex.finditer(script_data):
				match_offset = match.start() + 5
				x = map(lambda x : ord(x), list(match.groups()[0]))
				gmd_table = []
				for i in range(0, len(x), 2):
					gmd_table.append( (x[i], x[i+1]) )
				chip_tables.append(gmd_table)
				chip_offsets.append(match_offset)

			# Multiply zenny tables
			for match in zenny_regex.finditer(script_data):
				match_offset = match.start() + 5
				zenny_table = list(struct.unpack('<IIIIIIIIIIIIIIII', match.groups()[0]))
				zenny_tables.append(zenny_table)
				zenny_offsets.append(match_offset)

			# Compile the tables into one object
			output = GMDTable()
			output.zenny_tables = zenny_tables
			output.zenny_offsets = zenny_offsets
			output.chip_tables = chip_tables
			output.chip_offsets = chip_offsets
			# Also need this to write the tables back later
			output.script_ptr = script_ptr

			gmd_tables.append(output)

	rom.gmd_tables = gmd_tables

def write_gmds(rom):
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
	earliest_script = 999999999
	end_addr = -1
	# Apply changes to all scripts that were changed
	for gmd_table in rom.gmd_tables:
		script_ptr = gmd_table.script_ptr
		earliest_script = min(earliest_script, script_ptr)
		script_addr = rom.read_word(script_ptr) - 0x08000000
		script_data = rom.read_lz77(script_addr)
		end_addr = max(end_addr, rom.lz77_end)
		new_data = map(ord, script_data)

		# Change chip tables
		for offset, chip_table in zip(gmd_table.chip_offsets, gmd_table.chip_tables):
			for i in range(len(chip_table)):
				new_data[offset + 2*i    ] = chip_table[i][0]
				new_data[offset + 2*i + 1] = chip_table[i][1]

		# Change zenny tables
		for offset, zenny_table in zip(gmd_table.zenny_offsets, gmd_table.zenny_tables):
			zenny_str = struct.pack('<IIIIIIIIIIIIIIII', *zenny_table)
			for i in range(len(zenny_str)):
				new_data[offset + i] = ord(zenny_str[i])

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

def load_all(rom):
	load_enemies(rom)
	load_chips(rom)
	load_gmds(rom)

def write_all(rom):
	write_chips(rom)
	write_gmds(rom)
