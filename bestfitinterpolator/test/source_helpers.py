"""Source extraction for contract tests, including Python 3.7 without AST end positions."""
import ast
import io
import tokenize


def function_source(path, name):
    source = path.read_text(encoding='utf-8-sig')
    node = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == name)
    if hasattr(ast, 'get_source_segment'):
        return ast.get_source_segment(source, node)
    lines = source.splitlines(keepends=True)
    start = node.lineno
    # Python 3.7 reports the first decorator as a function's line number.
    while not lines[start - 1].lstrip().startswith(('def ', 'async def ')):
        start += 1
    if node.body and node.body[0].lineno == start:
        return lines[start - 1]
    depth = 0
    started = False
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.start[0] < start:
            continue
        if token.type == tokenize.INDENT:
            depth += 1
            started = True
        elif token.type == tokenize.DEDENT and started:
            depth -= 1
            if depth == 0:
                return ''.join(lines[start - 1:token.start[0] - 1])
    raise AssertionError('Function source not found: ' + name)
