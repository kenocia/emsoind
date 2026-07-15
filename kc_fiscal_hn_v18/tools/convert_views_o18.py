#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convierte atributos de vista Odoo 19 → attrs Odoo 18."""
from __future__ import annotations

import ast
import os
import re
import sys
from typing import Any


MODIFIERS = ('invisible', 'readonly', 'required', 'column_invisible')


def _field_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f'{_field_name(node.value)}.{node.attr}'
    raise ValueError(ast.dump(node))


def _literal(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_literal(e) for e in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_literal(e) for e in node.elts)
    if isinstance(node, ast.Name):
        return node.id
    raise ValueError(ast.dump(node))


def _bool_domain(node: ast.AST) -> list:
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.Or):
            parts = [_bool_domain(v) for v in node.values]
            prefixes = ['|'] * (len(parts) - 1)
            flat: list = []
            for p in parts:
                flat.extend(p)
            return prefixes + flat
        if isinstance(node.op, ast.And):
            out: list = []
            for v in node.values:
                out.extend(_bool_domain(v))
            return out
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        inner = _bool_domain(node.operand)
        if len(inner) == 1 and isinstance(inner[0], tuple):
            f, op, val = inner[0]
            if op == '=':
                return [(f, '!=', val)]
            if op == '!=':
                return [(f, '=', val)]
            if op == 'in':
                return [(f, 'not in', val)]
            if op == 'not in':
                return [(f, 'in', val)]
        if len(inner) == 1 and inner[0] == ('id', '!=', False):
            return [('id', '=', False)]
        return [('id', '=', -1)]
    if isinstance(node, ast.Compare):
        field = _field_name(node.left)
        out = []
        for op, comp in zip(node.ops, node.comparators):
            val = _literal(comp)
            if isinstance(op, ast.Eq):
                out.append((field, '=', val))
            elif isinstance(op, ast.NotEq):
                out.append((field, '!=', val))
            elif isinstance(op, ast.In):
                out.append((field, 'in', val))
            elif isinstance(op, ast.NotIn):
                out.append((field, 'not in', val))
            else:
                raise ValueError(type(op).__name__)
        return out
    if isinstance(node, ast.Name):
        return [(node.id, '!=', False)]
    if isinstance(node, ast.Constant):
        return [('id', '!=', False)] if node.value else [('id', '=', False)]
    raise ValueError(ast.dump(node))


def expr_to_domain(expr: str) -> list:
    expr = ' '.join(expr.split())
    if expr in ('1', 'True', 'true'):
        return [('id', '!=', False)]
    if expr in ('0', 'False', 'false'):
        return [('id', '=', False)]
    tree = ast.parse(expr, mode='eval')
    return _bool_domain(tree.body)


def normalize_multiline_attrs(content: str) -> str:
    """Une expresiones invisible/readonly en varias líneas."""
    pattern = re.compile(
        r'(?P<attr>invisible|readonly|required|column_invisible)="'
        r'(?P<val>[^"]*(?:\n\s*[^"\n>]+)*)"',
        re.MULTILINE,
    )

    def repl(m: re.Match) -> str:
        val = ' '.join(m.group('val').split())
        return f'{m.group("attr")}="{val}"'

    return pattern.sub(repl, content)


def convert_xpath_attributes(content: str, warnings: list) -> str:
    def repl(m: re.Match) -> str:
        attr = m.group(1)
        expr = ' '.join(m.group(2).split())
        try:
            domain = expr_to_domain(expr)
        except Exception as exc:
            warnings.append(f'xpath {attr}="{expr}": {exc}')
            return m.group(0)
        return f'<attribute name="attrs">{{"{attr}": {domain}}}</attribute>'

    return re.sub(
        r'<attribute name="(invisible|readonly|required|column_invisible)">\s*([^<]+?)\s*</attribute>',
        repl,
        content,
        flags=re.DOTALL,
    )


def convert_tag_modifiers(content: str, warnings: list) -> str:
    tag_re = re.compile(
        r'<(?P<tag>field|button|div|span|group|page|label|filter|setting|block|t|header|li|strong|a)'
        r'(?P<attrs>[^>]*?)/?>',
        re.DOTALL,
    )

    def process(m: re.Match) -> str:
        tag = m.group('tag')
        attrs_str = m.group('attrs')
        original = m.group(0)
        if not any(f'{mod}="' in attrs_str for mod in MODIFIERS):
            return original

        existing_attrs = {}
        am = re.search(r'\sattrs="(\{.*?\})"', attrs_str, re.DOTALL)
        if am:
            try:
                existing_attrs = ast.literal_eval(am.group(1))
            except (ValueError, SyntaxError):
                existing_attrs = {}

        for mod in MODIFIERS:
            mm = re.search(rf'\s{mod}="([^"]*)"', attrs_str)
            if not mm:
                continue
            expr = mm.group(1).strip()
            try:
                existing_attrs[mod] = expr_to_domain(expr)
            except Exception as exc:
                warnings.append(f'<{tag}> {mod}="{expr}": {exc}')
                return original

        # limpiar modificadores viejos
        cleaned = attrs_str
        for mod in MODIFIERS:
            cleaned = re.sub(rf'\s{mod}="[^"]*"', '', cleaned)
        cleaned = re.sub(r'\sattrs="\{.*?\}"', '', cleaned, flags=re.DOTALL)

        attrs_json = '{' + ', '.join(
            f"'{k}': {v}" for k, v in existing_attrs.items()
        ) + '}'
        cleaned = cleaned.rstrip()
        if original.rstrip().endswith('/>'):
            return f'<{tag}{cleaned} attrs="{attrs_json}"/>'
        return f'<{tag}{cleaned} attrs="{attrs_json}">'

    return tag_re.sub(process, content)


def convert_file(path: str) -> list:
    with open(path, 'r', encoding='utf-8') as f:
        original = f.read()
    warnings: list = []
    text = normalize_multiline_attrs(original)
    text = convert_xpath_attributes(text, warnings)
    text = convert_tag_modifiers(text, warnings)
    if text != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
    return warnings


def main(root: str) -> int:
    all_w = []
    for dp, _, fns in os.walk(root):
        if 'tools' in dp.split(os.sep):
            continue
        for fn in fns:
            if fn.endswith('.xml'):
                p = os.path.join(dp, fn)
                ws = convert_file(p)
                status = 'WARN' if ws else 'OK  '
                print(f'{status} {p}')
                all_w.extend(f'{p}: {w}' for w in ws)
    if all_w:
        print('\n--- Pendientes ---')
        for w in all_w:
            print(w)
    return 1 if all_w else 0


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(__file__))
    raise SystemExit(main(target))
