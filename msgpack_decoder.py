# msgpack_decoder.py

def decode(data):
    i = 0

    def read():
        nonlocal i
        val = data[i]
        i += 1
        return val

    def read_bytes(n):
        nonlocal i
        val = data[i:i+n]
        i += n
        return val

    def unpack():
        prefix = read()

        # FixInt (positive)
        if prefix <= 0x7f:
            return prefix

        # FixMap
        elif 0x80 <= prefix <= 0x8f:
            size = prefix & 0x0f
            obj = {}
            for _ in range(size):
                key = unpack()
                val = unpack()
                obj[key] = val
            return obj

        # FixArray
        elif 0x90 <= prefix <= 0x9f:
            size = prefix & 0x0f
            return [unpack() for _ in range(size)]

        # FixStr
        elif 0xa0 <= prefix <= 0xbf:
            size = prefix & 0x1f
            return read_bytes(size).decode()

        # uint8
        elif prefix == 0xcc:
            return read()

        # uint16
        elif prefix == 0xcd:
            return int.from_bytes(read_bytes(2), 'big')

        # uint32
        elif prefix == 0xce:
            return int.from_bytes(read_bytes(4), 'big')

        # str8
        elif prefix == 0xd9:
            size = read()
            return read_bytes(size).decode()

        else:
            raise ValueError(f"Unsupported prefix: {hex(prefix)}")

    return unpack()