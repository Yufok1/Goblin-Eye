"""Small, non-executing reader for inspected addon data tables, not a Lua runtime."""
from __future__ import annotations

import re
from typing import Any

SCALAR = re.compile(r"-?\d+(?:\.\d+)?|true\b|false\b|nil\b")
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class LuaLiteralReader:
    def __init__(self, text: str, position: int = 0):
        self.text = text
        self.position = position

    def skip(self) -> None:
        while self.position < len(self.text):
            if self.text[self.position].isspace():
                self.position += 1
            elif self.text.startswith("--", self.position):
                if self.text.startswith("--[", self.position):
                    raise ValueError("Unsupported block comment in data table")
                end = self.text.find("\n", self.position)
                self.position = len(self.text) if end < 0 else end + 1
            else:
                return

    def expect(self, token: str) -> None:
        self.skip()
        if not self.text.startswith(token, self.position):
            raise ValueError(f"Expected {token!r} at position {self.position}")
        self.position += len(token)

    def read(self, depth: int = 0) -> Any:
        if depth > 40:
            raise ValueError("Lua literal nesting is too deep")
        self.skip()
        if self.position >= len(self.text):
            raise ValueError("Truncated Lua literal")
        char = self.text[self.position]
        if char in "\"'":
            return self.string()
        if char == "{":
            return self.table(depth + 1)
        match = SCALAR.match(self.text, self.position)
        if not match:
            raise ValueError(f"Unsupported Lua expression at position {self.position}")
        token = match.group()
        self.position += len(token)
        if token in ("true", "false", "nil"):
            return {"true": True, "false": False, "nil": None}[token]
        return float(token) if "." in token else int(token)

    def string(self) -> str:
        quote = self.text[self.position]
        self.position += 1
        output: list[str] = []
        escapes = {"n": "\n", "r": "\r", "t": "\t", "a": "\a", "b": "\b", "f": "\f", "v": "\v", "\\": "\\", "\"": "\"", "'": "'"}
        while self.position < len(self.text):
            char = self.text[self.position]
            self.position += 1
            if char == quote:
                return "".join(output)
            if char == "\\":
                if self.position >= len(self.text):
                    break
                char = self.text[self.position]
                self.position += 1
                if char.isascii() and char.isdigit():
                    digits = char
                    while len(digits) < 3 and self.position < len(self.text) and self.text[self.position].isascii() and self.text[self.position].isdigit():
                        digits += self.text[self.position]
                        self.position += 1
                    if int(digits) > 255:
                        raise ValueError("Invalid Lua decimal escape")
                    output.append(chr(int(digits)))
                elif char in escapes:
                    output.append(escapes[char])
                else:
                    raise ValueError(f"Unsupported Lua string escape: {char!r}")
            elif char in "\r\n":
                raise ValueError("Unescaped newline in Lua string")
            else:
                output.append(char)
        raise ValueError("Unterminated Lua string")

    def table(self, depth: int) -> dict[Any, Any]:
        self.expect("{")
        result: dict[Any, Any] = {}
        sequence = 1
        while True:
            self.skip()
            if self.text.startswith("}", self.position):
                self.position += 1
                return result
            if self.text.startswith("[", self.position):
                self.expect("[")
                key = self.read(depth)
                if type(key) not in (int, str):
                    raise ValueError("Unsupported Lua table key")
                self.expect("]")
                self.expect("=")
                value = self.read(depth)
            else:
                # Lua's ``name = value`` table syntax is still a literal string
                # key.  Accept it without accepting identifiers as values or
                # executing any expressions.
                named = IDENTIFIER.match(self.text, self.position)
                if named:
                    after = named.end()
                    while after < len(self.text) and self.text[after].isspace():
                        after += 1
                    if after < len(self.text) and self.text[after] == "=":
                        key = named.group()
                        self.position = after + 1
                        value = self.read(depth)
                    else:
                        key, value = sequence, self.read(depth)
                        sequence += 1
                else:
                    key, value = sequence, self.read(depth)
                    sequence += 1
            if key in result:
                raise ValueError(f"Duplicate Lua key {key!r}")
            result[key] = value
            self.skip()
            if self.text.startswith((",", ";"), self.position):
                self.position += 1
            elif not self.text.startswith("}", self.position):
                raise ValueError(f"Unsupported Lua expression at position {self.position}")


def read_library_table(text: str, method: str, profession_argument: bool = False,
                       allowed_trailing_methods: tuple[str, ...] = (),
                       borrowed_fields: dict[int, dict[str, str]] | None = None) -> tuple[int | None, dict]:
    pattern = rf"^lib:{re.escape(method)}\(\s*" + (r"(\d+)\s*,\s*" if profession_argument else "")
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    if len(matches) != 1:
        raise ValueError(f"Expected one literal {method} call")
    match = matches[0]
    reader = LuaLiteralReader(text, match.end())
    value = reader.read()
    reader.expect(")")
    if not isinstance(value, dict):
        raise ValueError(f"{method} data must be a table")
    if profession_argument:
        reader.skip()
        seen = set()
        while reader.position < len(text):
            trailing = next((name for name in allowed_trailing_methods
                             if text.startswith(f"lib:{name}(", reader.position)), None)
            if trailing is None:
                raise ValueError(f"Unexpected data after {method}")
            reader.expect(f"lib:{trailing}(")
            if trailing == "LoadBorrowed":
                field = reader.read()
                reader.expect(",")
                origin = reader.read()
                reader.expect(",")
                ids = reader.read()
                if (method != "LoadCore" or borrowed_fields is None or field != "requiredSkill"
                        or not isinstance(origin, str) or not origin.strip() or len(origin) > 80
                        or not isinstance(ids, dict) or set(ids) != set(range(1, len(ids) + 1))):
                    raise ValueError("Unreviewed borrowed recipe metadata")
                for spell_id in ids.values():
                    if (type(spell_id) is not int or spell_id <= 0 or spell_id not in value
                            or not isinstance(value[spell_id], dict) or field not in value[spell_id]
                            or field in borrowed_fields.get(spell_id, {})):
                        raise ValueError("Invalid or duplicate borrowed recipe reference")
                    borrowed_fields.setdefault(spell_id, {})[field] = origin
            else:
                if trailing in seen:
                    raise ValueError(f"Duplicate trailing {trailing} call")
                seen.add(trailing)
                if not isinstance(reader.read(), dict):
                    raise ValueError("Expected trailing literal data table")
            reader.expect(")")
            reader.skip()
    return (int(match.group(1)) if profession_argument else None), value
