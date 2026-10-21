"""Shared buggy-source method identities for coverage and Person C's patch mapper."""

from dataclasses import asdict, dataclass
from collections import Counter
import hashlib
from pathlib import Path
import re

from tree_sitter import Language, Parser
import tree_sitter_java


@dataclass(frozen=True)
class JavaMethod:
    method_id: str
    source_path: str
    qualified_class: str
    method_name: str
    parameter_types: tuple[str, ...]
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    source: str
    source_sha256: str
    method_sha256: str
    source_encoding: str
    exact_binary_class: bool

    def to_dict(self):
        return asdict(self)


def parse_java(raw: bytes, source_path: str) -> tuple[list[JavaMethod], set[str]]:
    """Parse concrete methods/constructors, retaining full source and byte evidence.

    Types use source spelling with generics erased and type variables resolved
    to their first bound (Object when unbounded). Varargs become arrays;
    dimensions written after a parameter name are appended to its type.
    Anonymous/local classes use source-position suffixes, not guessed JVM IDs.
    """
    try:
        source = raw.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        source = raw.decode("latin-1")
        encoding = "latin-1"
    data = source.encode("utf-8")
    tree = Parser(Language(tree_sitter_java.language())).parse(data)
    if tree.root_node.has_error:
        raise ValueError(f"Java parse error in {source_path}; source mapping is not safe")
    digest = hashlib.sha256(raw).hexdigest()

    def text(node):
        return data[node.start_byte:node.end_byte].decode("utf-8")

    package = ""
    for node in tree.root_node.named_children:
        if node.type == "package_declaration":
            names = [child for child in node.named_children
                     if child.type in {"identifier", "scoped_identifier"}]
            if names:
                package = text(names[-1])
    methods = []
    classes = set()
    class_kinds = {"class_declaration", "interface_declaration", "enum_declaration",
                   "record_declaration", "annotation_type_declaration"}

    def extend_bounds(node, inherited):
        bounds = dict(inherited)
        parameters = node.child_by_field_name("type_parameters")
        for parameter in parameters.named_children if parameters is not None else []:
            name = next(child for child in parameter.named_children if child.type == "type_identifier")
            bound = next((child for child in parameter.named_children if child.type == "type_bound"), None)
            bounds[text(name)] = text(bound.named_children[0]) if bound is not None else "Object"
        return bounds

    def erase_type(typename, bounds, seen=()):
        result = []
        depth = 0
        for character in typename:
            if character == "<":
                depth += 1
            elif character == ">":
                depth -= 1
            elif not depth and not character.isspace():
                result.append(character)
        value = "".join(result)
        base = value.split("[", 1)[0]
        suffix = value[len(base):]
        if base in bounds:
            if base in seen:
                raise ValueError(f"Cyclic type variable bounds in {source_path}")
            value = erase_type(bounds[base], bounds, seen + (base,)) + suffix
        return value

    def visit(node, owner="", exact=True, inside_method=False, bounds=None):
        bounds = bounds or {}
        if node.type in class_kinds:
            bounds = extend_bounds(node, bounds)
            name = text(node.child_by_field_name("name"))
            if inside_method:
                name += f"@{node.start_point.row + 1}:{node.start_point.column + 1}"
                exact = False
            owner = (owner + "$" + name) if owner else ((package + ".") if package else "") + name
            classes.add(owner)
            inside_method = False
        if node.type in {"method_declaration", "constructor_declaration", "compact_constructor_declaration"}:
            bounds = extend_bounds(node, bounds)
            body = node.child_by_field_name("body")
            if body is not None and owner:
                name = "<init>" if "constructor" in node.type else text(node.child_by_field_name("name"))
                parameters = node.child_by_field_name("parameters")
                types = []
                for parameter in parameters.named_children if parameters is not None else []:
                    if parameter.type == "receiver_parameter":
                        continue
                    type_node = parameter.child_by_field_name("type")
                    if type_node is None and parameter.type == "spread_parameter":
                        type_node = next((child for child in parameter.named_children
                                          if child.type not in {"modifiers", "variable_declarator"}), None)
                    if type_node is None:
                        raise ValueError(f"Cannot identify parameter type in {source_path}: {text(parameter)}")
                    typename = re.sub(r"\s+", "", text(type_node))
                    dimensions = parameter.child_by_field_name("dimensions")
                    if dimensions is not None:
                        typename += re.sub(r"\s+", "", text(dimensions))
                    if parameter.type == "spread_parameter":
                        typename += "[]"
                    types.append(erase_type(typename, bounds))
                identifier = f"{source_path}::{owner}#{name}({','.join(types)})"
                body_source = text(node)
                methods.append(JavaMethod(identifier, source_path, owner, name, tuple(types),
                                          node.start_point.row + 1, node.end_point.row + 1,
                                          node.start_byte, node.end_byte, body_source, digest,
                                          hashlib.sha256(body_source.encode("utf-8")).hexdigest(), encoding, exact))
            inside_method = True
        for child in node.named_children:
            if child.type == "class_body" and node.type in {"object_creation_expression", "enum_constant"}:
                anonymous = owner + f"$anonymous@{node.start_point.row + 1}:{node.start_point.column + 1}"
                visit(child, anonymous, False, False, bounds)
            else:
                visit(child, owner, exact, inside_method, bounds)

    visit(tree.root_node)
    identifiers = [method.method_id for method in methods]
    if len(identifiers) != len(set(identifiers)):
        duplicates = [identifier for identifier, count in Counter(identifiers).items() if count > 1]
        raise ValueError(f"Duplicate method IDs in {source_path}: {duplicates}")
    return methods, classes


class SourceIndex:
    def __init__(self, checkout: Path, source_root: str):
        self.checkout = Path(checkout).resolve()
        root = (self.checkout / source_root).resolve()
        if not root.is_relative_to(self.checkout) or not root.is_dir():
            raise ValueError("Production source root is missing or outside the checkout")
        self.methods = []
        self.by_file = {}
        self.class_files = {}
        for path in sorted(root.rglob("*.java")):
            relative = path.relative_to(self.checkout).as_posix()
            methods, classes = parse_java(path.read_bytes(), relative)
            self.methods.extend(methods)
            self.by_file[relative] = methods
            for cls in classes:
                if cls in self.class_files and self.class_files[cls] != relative:
                    raise ValueError(f"Ambiguous source class: {cls}")
                self.class_files[cls] = relative
        if not self.methods:
            raise ValueError("No concrete production methods were parsed")

    def map_statement(self, statement: dict) -> dict:
        binary = statement["binary_class"]
        top = binary.split("$", 1)[0]
        path = self.class_files.get(binary) or self.class_files.get(top)
        if path is None:
            raise ValueError(f"No buggy-source file for instrumented class {binary}")
        name = statement["method_name"]
        if name == "<clinit>":
            return {"source_path": path, "method_id": None, "mapping_reason": "static_initializer"}
        candidates = []
        for method in self.by_file[path]:
            if not method.start_line <= statement["line"] <= method.end_line:
                continue
            if method.exact_binary_class and method.qualified_class != binary:
                continue
            if not method.exact_binary_class and method.qualified_class.split("$", 1)[0] != top:
                continue
            constructor_names = {"<init>", binary.rsplit("$", 1)[-1].rsplit(".", 1)[-1], binary.rsplit(".", 1)[-1]}
            if method.method_name == name or (method.method_name == "<init>" and name in constructor_names):
                candidates.append(method)
        if len(candidates) > 1:
            parameters = statement["parameter_signature"].split(",") if statement["parameter_signature"] else []
            candidates = [method for method in candidates if len(method.parameter_types) == len(parameters)]
            if len(candidates) > 1:
                def simple(typename):
                    return typename.rsplit(".", 1)[-1].rsplit("$", 1)[-1]
                candidates = [method for method in candidates
                              if list(map(simple, method.parameter_types)) == list(map(simple, parameters))]
            if len(candidates) > 1:
                raise ValueError(f"Ambiguous method mapping for {statement['statement_id']}")
        if candidates:
            return {"source_path": path, "method_id": candidates[0].method_id, "mapping_reason": "parsed_method"}
        # Fields, implicit default constructors, and generated enum helpers do not
        # have an existing declared method body. Retain their lines and counts.
        if name in {"<init>", binary.rsplit("$", 1)[-1].rsplit(".", 1)[-1], binary.rsplit(".", 1)[-1], "values", "valueOf"}:
            reason = "implicit_constructor_field_or_enum_helper"
        else:
            raise ValueError(f"Unexplained source mapping failure: {statement['statement_id']}")
        return {"source_path": path, "method_id": None, "mapping_reason": reason}
