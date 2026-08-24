# 结构配对检查（begin/end、case/endcase、module/endmodule、括号平衡）
# 用法：python struct_check.py <file.sv> [file2.sv ...]
# 预期：每个文件输出 => OK
import re, sys

def check(path):
    src = open(path, encoding='utf-8').read()
    src2 = re.sub(r'//[^\n]*', '', src)
    src2 = re.sub(r'/\*.*?\*/', '', src2, flags=re.S)
    tokens = re.findall(r'\b(begin|end|case|endcase|module|endmodule|function|endfunction|generate|endgenerate)\b', src2)
    pairs = {'begin':'end','case':'endcase','module':'endmodule','function':'endfunction','generate':'endgenerate'}
    stack = []; ok = True
    for t in tokens:
        if t in pairs:
            stack.append(t)
        else:
            if not stack or pairs[stack.pop()] != t:
                print(path, 'MISMATCH at', t); ok = False; break
    if stack:
        print(path, 'UNCLOSED', stack); ok = False
    print(path, 'braces', src2.count('{')-src2.count('}'),
          'parens', src2.count('(')-src2.count(')'),
          'brackets', src2.count('[')-src2.count(']'),
          '=> OK' if ok else '=> FAIL')

for f in sys.argv[1:]:
    check(f)
