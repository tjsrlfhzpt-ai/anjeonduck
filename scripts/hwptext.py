import olefile, zlib, struct, sys
def hwp_text(path):
    f = olefile.OleFileIO(path)
    hdr = f.openstream("FileHeader").read()
    compressed = hdr[36] & 1
    out = []
    secs = sorted([e for e in f.listdir() if e[0] == "BodyText"], key=lambda e: int(e[1][7:]))
    for e in secs:
        data = f.openstream(e).read()
        if compressed: data = zlib.decompress(data, -15)
        i = 0
        while i < len(data):
            h = struct.unpack_from("<I", data, i)[0]; i += 4
            tag, size = h & 0x3FF, (h >> 20) & 0xFFF
            if size == 0xFFF: size = struct.unpack_from("<I", data, i)[0]; i += 4
            if tag == 67:
                buf = data[i:i+size]; s = []; j = 0
                while j < len(buf):
                    c = struct.unpack_from("<H", buf, j)[0]
                    if c in (1,2,3,11,12,14,15,16,17,18,21,22,23): j += 16; continue
                    if c in (4,5,6,7,8,9,19,20): j += 16; continue
                    if c < 32: j += 2; s.append(" " if c in (9,10,13,24,30,31) else ""); continue
                    s.append(chr(c)); j += 2
                out.append("".join(s))
            i += size
    return "\n".join(out)
if __name__ == "__main__": print(hwp_text(sys.argv[1]))
