import re
import random

def virus_level(virus):
	if virus == 0 or virus >= 160:
		return -1
	if virus < 0x45:
		return (virus + 3) % 4
	elif virus < 0x4a:
		return 3
	else:
		return (virus + 1) % 4

def main(rom_path, output_path):
	raw_data = open(rom_path, 'rb').read()
	virus_data = open('virus_data.txt', 'r').read().strip()
	virus_data = map(lambda str: map(int, str.split(' ')), virus_data.split('\n'))
	randomized_data = list(raw_data)

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

	# Randomize all fights
	battle_regex = re.compile('(?s)\x00[\x01-\x03][\x01-\x03]\x00(?:.[\x01-\x06][\x01-\x03].)+\xff\x00\x00\x00')

	n_battles = 0
	for match in battle_regex.finditer(raw_data):
		# Sanity check
		if match.start() >= 0x22000:
			break
		n_battles += 1
		for i in range(match.start(), match.end(), 4):
			if raw_data[i + 3] == '\x01':
				virus_ind = ord(raw_data[i])
				randomized_data[i] = chr(virus_replace(virus_ind))
	open(output_path, 'wb').write(''.join(randomized_data))
	print 'randomized %d battles' % n_battles

if __name__ == '__main__':
	main('white.gba', 'white_randomized.gba')
