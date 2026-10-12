"""Read immutable library/CLI source as AST data only; execute no historical product code."""
import subprocess


def checkpoint_graph(root, checkpoint, analyzer):
    names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', checkpoint], cwd=root, text=True).splitlines()
    names = [name for name in names if name.endswith('.py') and ('/' not in name or name.startswith(('tools/', 'stocklookup_core/')))]
    request = ''.join(checkpoint+':'+name+'\n' for name in names).encode()
    raw = subprocess.run(['git', 'cat-file', '--batch'], cwd=root, input=request, capture_output=True, check=True).stdout
    sources, offset = {}, 0
    for name in names:
        end = raw.index(b'\n', offset); size = int(raw[offset:end].split()[-1])
        sources[name] = raw[end+1:end+1+size].decode('utf-8-sig')
        offset = end+size+2
    return analyzer.scan_sources(sources)
