import sys
import typing as t
from dataclasses import dataclass, field

__all__ = ("query", "parse", "Json", "Error", "ParseError")


Json = t.Union[None, int, float, t.Dict[str, "Json"], t.List["Json"]]
Key = t.Union[t.Literal["*"], str]
Slice = slice


class Error(Exception):
    ...


class ParseError(Error):
    ...


def _apply_star(results: t.Sequence[Json]) -> t.List[Json]:
    new_results: t.List[Json] = []
    for result in results:
        if isinstance(result, dict):
            new_results.extend(result.values())
        if isinstance(result, list):
            new_results.extend(result)
    return new_results


def _apply_key(results: t.Sequence[Json], key: Key) -> t.List[Json]:
    if isinstance(key, str):
        if key == "*":
            return _apply_star(results)
        else:
            return [result[key] for result in results if isinstance(result, dict) and key in result]


def _apply_slice(results: t.Sequence[Json], slice: Slice) -> t.List[Json]:
    return [value for result in results if isinstance(result, list) for value in result[slice]]


def _recursive_descent_key(results: t.Sequence[Json], key: t.Union[Key, Slice]) -> t.List[Json]:
    new_results: t.List[Json] = []
    todo: t.List[Json] = [*(results[::-1])]
    while len(todo) > 0:
        curr = todo.pop()
        if key == "*":
            new_values = _apply_star([curr])
            new_results.extend(new_values)
            todo.extend(new_values[::-1])
        elif isinstance(curr, dict):
            if isinstance(key, str) and key in curr:
                new_results.append(curr[key])
            values = list(curr.values())[::-1]
            todo.extend(values)
        elif isinstance(curr, list):
            if isinstance(key, Slice):
                new_results.extend(curr[key])
            todo.extend(curr[::-1])
    return new_results


@dataclass
class JsonPathQueryRunner:
    data: Json
    path: str
    idx: int = field(default=0, init=False)
    _curr: t.Optional[str] = field(default=None, init=False)
    results: t.List[Json] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if not self.at_end():
            self._curr = self.path[0]

    def query(self) -> t.List[Json]:
        self.results = [self.data]
        self.consume("$", "at the beginning of JSONPath")
        self.child()
        return self.results

    def child(self) -> None:
        if self.at_end():
            return
        if self.match("."):
            if self.match("."):
                self.recursive_descent()
            else:
                key = self.key()
                if isinstance(key, str):
                    self.results = _apply_key(self.results, key)
                else:
                    self.results = _apply_slice(self.results, key)
        elif self.match("["):
            key = self.bracket()
            if isinstance(key, str):
                self.results = _apply_key(self.results, key)
            elif isinstance(key, slice):
                self.results = _apply_slice(self.results, key)
        else:
            assert False, f"Expected '.' or '[' at pos: {self.idx + 1}, got: '{self._curr}'"
        self.child()

    def recursive_descent(self) -> None:
        if self.match("["):
            key = self.bracket()
        else:
            key = self.key()
        self.results = _recursive_descent_key(self.results, key)

    def key(self) -> t.Union[str, Slice]:
        if self.at_end():
            raise ParseError("Expected key at the end of JSONPath.")
        if any(self.match(c) for c in (".", "$", "[")):
            raise ParseError(f"Key name can't start with a '{self.prev()}' (pos: {self.idx + 1})")

        slice = self.slice()
        if slice is not None:
            return slice

        k = []
        while not self.at_end() and self.curr not in [".", "["]:
            if self.curr in ["'", '"']:
                raise ParseError(f"Forbidden char in key value: '{self.curr}'.")
            k.append(self.curr)
            self.advance()
        return "".join(k)

    def bracket(self) -> t.Union[str, Slice]:
        if self.match("*"):
            self.consume("]", "after '*'")
            return "*"
        else:
            if self.match("'"):
                quote_type = "'"
                expect_num = False
            elif self.match('"'):
                quote_type = '"'
                expect_num = False
            else:
                quote_type = None
                expect_num = True
            if expect_num:
                result = self.slice()
                if result is None:
                    raise ParseError(f"Expected a subscript or a slice after '[' (pos {self.idx}).")
                self.consume("]", "after numerical subscript or slice")
                return result
            else:
                # TODO: refactor to get rid of this assertion
                assert quote_type is not None
                k = []
                str_beg = self.idx
                while not self.at_end() and self._curr != quote_type:
                    k.append(self._curr)
                    self.advance()
                if self.at_end():
                    raise ParseError(f"String started at pos {str_beg} was not closed.")
                if not self.match(quote_type):
                    assert False, "Internal error."
                self.consume("]", f"after {quote_type}")
                return "".join(k)

    def slice(self) -> t.Optional[Slice]:
        start = self.num()
        if self.match(":"):
            end = self.num()
            if self.match(":"):
                step = self.num()
                return slice(start, end, step)
            return slice(start, end, None)
        elif start is None:
            return None
        else:
            if start == -1:
                return slice(start, None, None)
            else:
                return slice(start, start + 1, None)

    def num(self) -> t.Optional[int]:
        k = []
        if self.match("-"):
            k.append("-")
        while not self.at_end() and self.curr.isnumeric():
            k.append(self.curr)
            self.advance()
        if len(k) == 0:
            return None
        return int("".join(k))

    def match(self, c: str) -> bool:
        assert len(c) == 1
        if self._curr == c:
            self.advance()
            return True
        return False

    @property
    def curr(self) -> str:
        assert self._curr is not None
        return self._curr

    def prev(self) -> str:
        return self.path[self.idx - 1]

    def advance(self) -> None:
        assert not self.at_end()
        self.idx += 1
        if not self.at_end():
            self._curr = self.path[self.idx]
        else:
            self._curr = None

    def at_end(self) -> bool:
        return self.idx >= len(self.path)

    def consume(self, c: str, where: str) -> None:
        if self.at_end() or not self.match(c):
            raise ParseError(f"Expected '{c}' {where} (pos {self.idx}).")


def query(data: Json, path: str) -> t.List[Json]:
    return JsonPathQueryRunner(data, path).query()


def parse(path: str) -> None:
    JsonPathQueryRunner({}, path).query()


def main() -> None:
    data: Json = {
        "a": 123,
        "b": {"c": 234},
        "c": [{"d": {"e": [1, 2, 3]}}, {"d": {"e": [12, 13, 14]}}],
    }
    path = sys.argv[1]
    result = query(data, path)
    import pprint

    pprint.pprint(result)


if __name__ == "__main__":
    main()
