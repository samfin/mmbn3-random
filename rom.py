import struct

# Wrapper class around low level reads/writes
class Rom(object):
	def __init__(self, rom_path):
		self.rom_data = open(rom_path, 'rb').read()
		# Python why you no let me modify strings
		self.buffer = list(self.rom_data)
		self.w_offset = 0
		self.r_offset = 0
		self.stack = []

	def seekr(self, offset):
		self.r_offset = offset
	def seekw(self, offset):
		self.w_offset = offset
	def seek(self, offset):
		self.seekr(offset)
		self.seekw(offset)
	def save_offsets(self):
		self.stack.append((self.r_offset, self.w_offset))
	def load_offsets(self):
		self.r_offset, self.w_offset = self.stack.pop()

	# Generally, providing an offset = don't change the state
	# Not providing an offset = use the stored offset and increment it
	# Also changes the write offset, careful!!
	def read(self, n, offset = -1):
		if offset == -1:
			offset = self.r_offset
			self.w_offset = self.r_offset
			self.r_offset += n
		assert(offset >= 0)
		assert(offset + n <= len(self.rom_data))
		return self.rom_data[offset : offset + n]

	def read_byte(self, offset = -1):
		return ord(self.read(1, offset))
	def read_halfword(self, offset = -1):
		return struct.unpack('<H', self.read(2, offset))[0]
	def read_word(self, offset = -1):
		return struct.unpack('<I', self.read(4, offset))[0]
	def read_dblword(self, offset = -1):
		return struct.unpack('<Q', self.read(8, offset))[0]

	def read_lz77(self, offset = -1):
		if offset != -1:
			self.save_offsets()
			self.seek(offset)
		decompressed_size = self.read_word() >> 8;
		output = []
		while len(output) < decompressed_size:
			flags = self.read_byte()
			for i in range(8):
				is_special = bool(flags & 0x80)
				if is_special:
					a = self.read_byte()
					b = self.read_byte()
					x_len = (a >> 4) + 3
					x_offset = (b + ((a & 0xf) << 8))
					start = len(output) - 1 - x_offset
					for j in range(x_len):
						output.append(output[start + j])
				else:
					output.append(self.read_byte())
				flags <<= 1;
		output = output[:decompressed_size]

		self.lz77_end = self.r_offset
		if offset != -1:
			self.load_offsets()
		return ''.join(map(lambda x : chr(x), output))

	def write(self, data, offset = -1):
		if offset == -1:
			offset = self.w_offset
			self.w_offset += len(data)
		assert(offset >= 0)
		assert(offset + len(data) <= len(self.rom_data))
		for i in range(len(data)):
			self.buffer[offset + i] = data[i]

	def write_byte(self, x, offset = -1):
		return self.write(chr(x), offset)
	def write_halfword(self, x, offset = -1):
		return self.write(struct.pack('<H', x), offset)
	def write_word(self, x, offset = -1):
		return self.write(struct.pack('<I', x), offset)
	def write_dblword(self, x, offset = -1):
		return self.write(struct.pack('<Q', x), offset)

	def lz77_compress(self, data):
		ops = []
		i = 0
		data_len = len(data)
		while i < data_len:
			lo = 2
			hi = min(18, len(data) - i)
			start = max(0, i - 4096)
			last_match_ind = -1
			while lo < hi:
				mid = (lo + hi + 1) / 2
				ss = data[i : i + mid]
				t = data.find(ss, start)
				if t < i:
					# match found
					last_match_ind = t
					lo = mid
				else:
					hi = mid - 1
			if lo < 3:
				ops.append((0, ord(data[i])))
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
