import sys, os, re

# parse roman number (1-39)
def roman_number(r):
    if m := re.match("(|X|XX|XXX)(|I(?=X$|V$))(X?)(V?)(|I|II|III)$", r.upper()):
        x1 = len(m.group(1))
        i1 = len(m.group(2))
        x2 = len(m.group(3))
        v1 = len(m.group(4))
        i2 = len(m.group(5))
        return x1 * 10 - i1 + x2 * 10 + v1 * 5 + i2
    raise ValueError(f"invalid roman number: {r}")

dir = ""
no = 0
text = ""
def write():
    global dir, no, text
    if dir:
        with open(f"{dir}/{no:02}.txt", "w") as file:
            file.write(text)
        text = ""
while (line := sys.stdin.readline()):
    line = line.rstrip()
    if re.match("[A-Z]+$", line):
        pass
    elif line in ["Inferno", "Purgatorio", "Paradiso"]:
        write()
        dir = line.lower()
        if not os.path.exists(dir):
            os.mkdir(dir)
        line = sys.stdin.readline().rstrip()
        if not (m:= re.match(r"Canto (\w+)", line)):
            raise ValueError(f"invalid line: {line}")
        no = roman_number(m.group(1))
    elif line.lstrip().startswith("*** END"):
        write()
        break
    elif line and dir:
        text += line.lstrip() + "\n"
