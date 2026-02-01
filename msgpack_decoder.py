# msgpack_decoder.py (MicroPython-friendly)
import struct

def decode(data):
    i = 0
    n = len(data)

    def read():
        nonlocal i
        if i >= n:
            raise ValueError("Unexpected end of data")
        b = data[i]
        i += 1
        return b

    def read_bytes(k):
        nonlocal i
        if i + k > n:
            raise ValueError("Unexpected end of data")
        b = data[i:i+k]
        i += k
        return b

    def unpack():
        prefix = read()

        # positive fixint
        if prefix <= 0x7f:
            return prefix

        # fixmap
        if 0x80 <= prefix <= 0x8f:
            size = prefix & 0x0f
            obj = {}
            for _ in range(size):
                key = unpack()
                val = unpack()
                obj[key] = val
            return obj

        # fixarray
        if 0x90 <= prefix <= 0x9f:
            size = prefix & 0x0f
            return [unpack() for _ in range(size)]

        # fixstr
        if 0xa0 <= prefix <= 0xbf:
            size = prefix & 0x1f
            return read_bytes(size).decode()

        # nil
        if prefix == 0xc0:
            return None

        # (0xc1 is never used)

        # bool
        if prefix == 0xc2:
            return False
        if prefix == 0xc3:
            return True

        # bin8/bin16/bin32 (optional: implement if you send bytes)
        if prefix == 0xc4:
            size = read()
            return bytes(read_bytes(size))
        if prefix == 0xc5:
            size = int.from_bytes(read_bytes(2), 'big')
            return bytes(read_bytes(size))
        if prefix == 0xc6:
            size = int.from_bytes(read_bytes(4), 'big')
            return bytes(read_bytes(size))

        # float32 / float64
        if prefix == 0xca:  # float32
            return struct.unpack('>f', read_bytes(4))[0]
        if prefix == 0xcb:  # float64
            return struct.unpack('>d', read_bytes(8))[0]

        # uint8/16/32/64
        if prefix == 0xcc:
            return read()
        if prefix == 0xcd:
            return int.from_bytes(read_bytes(2), 'big')
        if prefix == 0xce:
            return int.from_bytes(read_bytes(4), 'big')
        if prefix == 0xcf:
            return int.from_bytes(read_bytes(8), 'big')

        # int8/16/32/64
        if prefix == 0xd0:
            return struct.unpack('>b', read_bytes(1))[0]
        if prefix == 0xd1:
            return struct.unpack('>h', read_bytes(2))[0]
        if prefix == 0xd2:
            return struct.unpack('>i', read_bytes(4))[0]
        if prefix == 0xd3:
            return struct.unpack('>q', read_bytes(8))[0]

        # str8/str16/str32
        if prefix == 0xd9:
            size = read()
            return read_bytes(size).decode()
        if prefix == 0xda:
            size = int.from_bytes(read_bytes(2), 'big')
            return read_bytes(size).decode()
        if prefix == 0xdb:
            size = int.from_bytes(read_bytes(4), 'big')
            return read_bytes(size).decode()

        # array16/array32
        if prefix == 0xdc:
            size = int.from_bytes(read_bytes(2), 'big')
            return [unpack() for _ in range(size)]
        if prefix == 0xdd:
            size = int.from_bytes(read_bytes(4), 'big')
            return [unpack() for _ in range(size)]

        # map16/map32
        if prefix == 0xde:
            size = int.from_bytes(read_bytes(2), 'big')
            obj = {}
            for _ in range(size):
                k = unpack()
                v = unpack()
                obj[k] = v
            return obj
        if prefix == 0xdf:
            size = int.from_bytes(read_bytes(4), 'big')
            obj = {}
            for _ in range(size):
                k = unpack()
                v = unpack()
                obj[k] = v
            return obj

        # negative fixint (-32..-1): 0xe0..0xff
        if prefix >= 0xe0:
            return prefix - 0x100

        raise ValueError("Unsupported prefix: 0x{:02x}".format(prefix))

    return unpack()