"""Read/write JUCE VST3 host state (VC2! + XML), so Surge XT .fxp patches can be loaded in DawDreamer."""
import base64, re, struct
CH = ".ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+"

def jdec(s):
    size, data = s.split(".", 1)
    out = bytearray(int(size)); pos = 0
    for c in data:
        v = CH.index(c)
        for b in range(6):
            if v >> b & 1 and (pos + b) // 8 < len(out):
                out[(pos + b) // 8] |= 1 << ((pos + b) % 8)
        pos += 6
    return bytes(out)

def jenc(b):
    nbits = len(b) * 8; out = []
    for pos in range(0, nbits, 6):
        v = 0
        for i in range(6):
            p = pos + i
            if p < nbits and b[p // 8] >> (p % 8) & 1: v |= 1 << i
        out.append(CH[v])
    return f"{len(b)}." + "".join(out)

def read(path):
    raw = open(path, "rb").read()
    return raw[8:].decode().rstrip("\0")

def component(xml):
    return jdec(re.search(r"<IComponent>(.*?)</IComponent>", xml, re.S).group(1))

def write(path, xml, comp):
    xml = re.sub(r"<IComponent>.*?</IComponent>", lambda m: f"<IComponent>{jenc(comp)}</IComponent>", xml, flags=re.S)
    body = xml.encode() + b"\0"
    open(path, "wb").write(b"VC2!" + struct.pack("<I", len(body)) + body)
