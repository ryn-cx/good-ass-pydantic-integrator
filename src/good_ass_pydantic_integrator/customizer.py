# TODO: Validate
# TODO: Go through this file to see if all of this is still used.
"""Post-generation customization of Pydantic models."""

import ast
from dataclasses import dataclass, field
from typing import TypeGuard


@dataclass
class ReplacementField:
    """Replacement fields to be used with GAPICustomizer.

    Attributes:
        class_name: The name of the class containing the field to replace.
        field_name: The name of the existing field to replace.
        new_field: The new field definition as a string. Either a full annotated
            assignment like ``"my_field: int = Field(...)"`` or just the
            annotation portion like ``"int = Field(...)"`` — in the latter case
            ``field_name`` is prepended automatically.
    """

    class_name: str
    field_name: str
    new_field: str

    def generate_field_ast(self) -> list[ast.stmt]:
        """Generate the replacement field as a list of AST statement nodes."""
        body = ast.parse(self.new_field).body
        if body and isinstance(body[0], ast.AnnAssign):
            return body
        return ast.parse(f"{self.field_name}: {self.new_field}").body


@dataclass
class ReplacementType:
    """Replace only the type annotation of an existing field.

    Unlike ``ReplacementField`` which replaces the entire field definition, this
    preserves the field name, alias, default value, and other attributes.

    Attributes:
        class_name: The name of the class containing the field.
        field_name: The name of the field whose type to replace.
        new_type: The new type annotation as a string, e.g. ``"int"``.
    """

    class_name: str
    field_name: str
    new_type: str

    def generate_type_ast(self) -> ast.expr:
        """Generate the replacement type as an AST expression node."""
        stmt = ast.parse(f"x: {self.new_type}").body[0]
        if not isinstance(stmt, ast.AnnAssign):  # pragma: no cover
            msg = f"Failed to parse type annotation: {self.new_type!r}"
            raise TypeError(msg)
        return stmt.annotation


@dataclass
class CustomSerializer:
    """Custom serializers to be used with GAPICustomizer.

    Attributes:
        field_name: The name of the field to serialize.
        serializer_code: The serializer body as a string or list of lines.
        output_type: The return type annotation.
        class_name: The class to add the serializer to. If None, applies to all
            classes with the matching field.
    """

    field_name: str
    serializer_code: str | list[str]
    output_type: str = field(kw_only=True)
    class_name: str | None = field(default=None, kw_only=True)

    def create_serializer_ast(self, input_type: str) -> list[ast.stmt]:
        """Generate the ``@field_serializer`` decorated method as AST nodes.

        Args:
            input_type: The type annotation for the ``value`` parameter,
                derived from the existing field.

        Returns:
            The serializer method as a list of AST statement nodes.
        """
        serializer_code = self.serializer_code
        if isinstance(serializer_code, str):
            serializer_code = serializer_code.split("\n")

        source = (
            f'@field_serializer("{self.field_name}")\n'
            f"def serialize_{self.field_name}"
            f"(self, value: {input_type})"
            f" -> {self.output_type}:\n"
            "    "
            f"{'\n    '.join(serializer_code)}"
        )
        return ast.parse(source).body


# Pydantic type names datamodel-code-generator emits for the formatted-string
# strategies (uuid, date-time, date, time, duration, ipv4, ipv6). Each is a
# stricter parse of a value that is also a valid ``str``. When such a type is
# unioned with a plain ``str``, pydantic's default *smart* union resolves the
# value to ``str`` (the lossless, no-coercion match) regardless of member order,
# discarding the narrower type. See ``_apply_left_to_right_unions``.
_NARROW_STRING_TYPES = frozenset(
    {
        "UUID",
        "AwareDatetime",
        "datetime",
        "date",
        "time",
        "timedelta",
        "IPv4Address",
        "IPv6Address",
    },
)


class GAPICustomizer:
    """Compiles and applies customizations to generated models."""

    def __init__(self) -> None:
        """Initialize GAPICustomizer."""
        self.replacement_fields: list[ReplacementField] = []
        self.replacement_types: list[ReplacementType] = []
        self.custom_serializers: list[CustomSerializer] = []
        self.additional_imports: list[str] = []

    def add_replacement_field(
        self,
        class_name: str,
        field_name: str,
        new_field: str,
    ) -> None:
        """Add a replacement field to apply during model generation.

        Args:
            class_name: The class containing the field to replace.
            field_name: The name of the field to replace.
            new_field: The new field definition. Either a full annotated
                assignment like ``"field: int"`` or just the annotation
                portion like ``"int = Field(...)"`` — in the latter case
                ``field_name`` is prepended automatically.
        """
        replacement_field = ReplacementField(
            class_name=class_name,
            field_name=field_name,
            new_field=new_field,
        )
        self.replacement_fields.append(replacement_field)

    def add_replacement_type(
        self,
        class_name: str,
        field_name: str,
        new_type: str,
    ) -> None:
        """Add a type replacement to apply during model generation.

        Unlike ``add_replacement_field``, this only changes the type annotation
        while preserving the field name, alias, default value, and other attributes.

        Args:
            class_name: The class containing the field.
            field_name: The name of the field whose type to replace.
            new_type: The new type annotation, e.g. ``"int"``.
        """
        replacement_type = ReplacementType(
            class_name=class_name,
            field_name=field_name,
            new_type=new_type,
        )
        self.replacement_types.append(replacement_type)

    def add_custom_serializer(
        self,
        field_name: str,
        serializer_code: str | list[str],
        output_type: str,
        class_name: str | None = None,
    ) -> None:
        """Add a custom serializer to apply during model generation.

        Args:
            field_name: The field to add the serializer to.
            serializer_code: The serializer body as a string or list of lines.
                Indentation is not required.
            output_type: Return type annotation for the serializer.
            class_name: The class to add the serializer to. If None, applies to
                all classes with the matching field.
        """
        custom_serializer = CustomSerializer(
            class_name=class_name,
            field_name=field_name,
            serializer_code=serializer_code,
            output_type=output_type,
        )
        self.custom_serializers.append(custom_serializer)

    def add_additional_import(self, import_statement: str) -> None:
        """Add an additional import to apply during model generation.

        Args:
            import_statement: A full import statement, e.g. ``"from pydantic import
                Field"``.
        """
        self.additional_imports.append(import_statement)

    def apply_customizations(self, model_content: str) -> str:
        """Apply all customizations to the model content.

        Args:
            model_content: The generated Pydantic model content as a string.

        Returns:
            The customized model content.
        """
        tree = ast.parse(model_content)

        class_nodes: dict[str, ast.ClassDef] = {
            node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
        }

        self._replace_untyped_lists(class_nodes)
        pinned_union = self._apply_left_to_right_unions(class_nodes)
        self._apply_replacement_fields(class_nodes)
        self._apply_replacement_types(class_nodes)
        self._apply_custom_serializers(class_nodes)

        additional_imports = list(self.additional_imports)
        if self.custom_serializers:
            additional_imports.append("from pydantic import field_serializer")
        # The left-to-right pass may introduce the first Field(...) call in a
        # model that had no aliases and therefore no Field import.
        if pinned_union and not self._imports_name(tree, "Field"):
            additional_imports.append("from pydantic import Field")
        self._apply_additional_imports(tree, additional_imports)

        ast.fix_missing_locations(tree)
        return ast.unparse(tree) + "\n"

    def _apply_replacement_fields(self, class_nodes: dict[str, ast.ClassDef]) -> None:
        """Replace matching fields in class bodies with custom definitions."""
        for replacement_field in self.replacement_fields:
            class_node = class_nodes.get(replacement_field.class_name)
            if not class_node:
                msg = (
                    f"Class {replacement_field.class_name!r} not found in"
                    " generated models"
                )
                raise ValueError(msg)

            for i, node in enumerate(class_node.body):
                if self._is_field_node(node, replacement_field.field_name):
                    class_node.body[i : i + 1] = replacement_field.generate_field_ast()
                    break
            else:
                msg = (
                    f"Field {replacement_field.field_name!r} not found in"
                    f" class {replacement_field.class_name!r}"
                )
                raise ValueError(msg)

    def _apply_replacement_types(self, class_nodes: dict[str, ast.ClassDef]) -> None:
        """Replace type annotations on matching fields in class bodies."""
        for replacement_type in self.replacement_types:
            class_node = class_nodes.get(replacement_type.class_name)
            if not class_node:
                msg = (
                    f"Class {replacement_type.class_name!r} not found in"
                    " generated models"
                )
                raise ValueError(msg)

            for node in class_node.body:
                if self._is_field_node(node, replacement_type.field_name):
                    node.annotation = replacement_type.generate_type_ast()
                    break
            else:
                msg = (
                    f"Field {replacement_type.field_name!r} not found in"
                    f" class {replacement_type.class_name!r}"
                )
                raise ValueError(msg)

    def _apply_custom_serializers(self, class_nodes: dict[str, ast.ClassDef]) -> None:
        """Insert serializer methods into class bodies."""
        if not self.custom_serializers:
            return

        for custom_serializer in self.custom_serializers:
            field_name = custom_serializer.field_name
            # If a class_name is defined only add the serializer to that class.
            if class_name := custom_serializer.class_name:
                if class_name not in class_nodes:
                    msg = f"Class {class_name!r} not found in generated models"
                    raise ValueError(msg)
                input_type = self._get_field_type(class_nodes[class_name], field_name)
                serializer_ast = custom_serializer.create_serializer_ast(input_type)
                class_nodes[class_name].body.extend(serializer_ast)
            # If a class_name is not defined add the serializer to all classes that have
            # a matching field name.
            else:
                for class_node in class_nodes.values():
                    if self._has_field(class_node, field_name):
                        input_type = self._get_field_type(class_node, field_name)
                        serializer_ast = custom_serializer.create_serializer_ast(
                            input_type,
                        )
                        class_node.body.extend(serializer_ast)

    @staticmethod
    def _apply_additional_imports(tree: ast.Module, imports: list[str]) -> None:
        """Insert additional import statements into the module."""
        for i, import_line in enumerate(imports):
            tree.body.insert(i, ast.parse(import_line).body[0])

    @staticmethod
    def _replace_untyped_lists(
        class_nodes: dict[str, ast.ClassDef],
    ) -> None:
        """Replace ``list[Any]`` with ``list[None]`` in annotations.

        If the first file has an empty list it will be typed as list[Any], if the next
        file has a non-empty list the type will remain a list[Any] which will cause
        these values to have no type information. Converting list[Any] to list[None]
        allows these fields to be identified and replaced with the correct type
        information.
        """
        for class_node in class_nodes.values():
            for node in class_node.body:
                if not (
                    isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name)
                ):
                    continue
                for child in ast.walk(node.annotation):
                    if GAPICustomizer._is_untyped_list(child):
                        child.slice = ast.Constant(value=None)

    @staticmethod
    def _imports_name(tree: ast.Module, name: str) -> bool:
        """Check whether ``name`` is already imported at module level."""
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and any(
                alias.asname == name or (alias.asname is None and alias.name == name)
                for alias in node.names
            ):
                return True
        return False

    @classmethod
    def _apply_left_to_right_unions(
        cls,
        class_nodes: dict[str, ast.ClassDef],
    ) -> bool:
        """Preserve narrow string types in ``<narrow> | str`` unions.

        A value that is a valid UUID/datetime/etc. is also a valid ``str``, so
        pydantic's default *smart* union resolves it to ``str`` and the narrower
        type is lost. This happens whenever type inference widens a field that is
        usually (say) a UUID but sometimes an arbitrary string.

        For every field whose annotation unions a narrow string type with a plain
        ``str``, reorder the narrow types ahead of ``str`` and pin the field to
        ``union_mode='left_to_right'`` so pydantic tries the narrow parse first
        and only falls back to ``str`` when it fails.

        Returns:
            ``True`` if any field was modified.
        """
        mutated = False
        for class_node in class_nodes.values():
            for node in class_node.body:
                if not (
                    isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name)
                ):
                    continue
                members = cls._flatten_union(node.annotation)
                if members is None:
                    continue
                names = {m.id for m in members if isinstance(m, ast.Name)}
                if "str" not in names or names.isdisjoint(_NARROW_STRING_TYPES):
                    continue
                node.annotation = cls._build_union(cls._narrow_first(members))
                cls._pin_left_to_right(node)
                mutated = True
        return mutated

    @staticmethod
    def _flatten_union(annotation: ast.expr) -> list[ast.expr] | None:
        """Return the members of a PEP 604 ``a | b | c`` union, else ``None``.

        Only the ``|`` operator form is produced by the generator, so
        ``Union[...]`` / ``Optional[...]`` subscripts are intentionally ignored.
        """
        if not (isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr)):
            return None
        left = GAPICustomizer._flatten_union(annotation.left)
        left_members = left if left is not None else [annotation.left]
        return [*left_members, annotation.right]

    @staticmethod
    def _narrow_first(members: list[ast.expr]) -> list[ast.expr]:
        """Move narrow string types ahead of the rest, preserving relative order."""
        narrow = [
            m
            for m in members
            if isinstance(m, ast.Name) and m.id in _NARROW_STRING_TYPES
        ]
        rest = [
            m
            for m in members
            if not (isinstance(m, ast.Name) and m.id in _NARROW_STRING_TYPES)
        ]
        return narrow + rest

    @staticmethod
    def _build_union(members: list[ast.expr]) -> ast.expr:
        """Fold ``members`` back into a left-associative ``a | b | c`` union."""
        union = members[0]
        for member in members[1:]:
            union = ast.BinOp(left=union, op=ast.BitOr(), right=member)
        return union

    @staticmethod
    def _pin_left_to_right(node: ast.AnnAssign) -> None:
        """Add ``union_mode='left_to_right'`` to a field's ``Field(...)`` call."""
        keyword = ast.keyword(
            arg="union_mode",
            value=ast.Constant(value="left_to_right"),
        )
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "Field"
        ):
            if not any(kw.arg == "union_mode" for kw in value.keywords):
                value.keywords.append(keyword)
        elif value is None:
            # Required field with no default: Field() alone keeps it required.
            node.value = ast.Call(
                func=ast.Name(id="Field", ctx=ast.Load()),
                args=[],
                keywords=[keyword],
            )
        else:
            # Plain default (e.g. ``= None``): fold it into Field(default=...).
            node.value = ast.Call(
                func=ast.Name(id="Field", ctx=ast.Load()),
                args=[],
                keywords=[ast.keyword(arg="default", value=value), keyword],
            )

    @staticmethod
    def _is_untyped_list(node: ast.AST) -> TypeGuard[ast.Subscript]:
        """Check if an AST node has an annotation of ``list[Any]``."""
        return (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and (node.value.id in ("list", "List"))
            and isinstance(node.slice, ast.Name)
            and node.slice.id == "Any"
        )

    @staticmethod
    def _is_field_node(node: ast.stmt, field_name: str) -> TypeGuard[ast.AnnAssign]:
        """Check whether an AST node is an annotated assignment with the given name."""
        return (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == field_name
        )

    @staticmethod
    def _get_field_type(class_node: ast.ClassDef, field_name: str) -> str:
        """Return the type annotation string for a field in a class AST node."""
        for node in class_node.body:
            if GAPICustomizer._is_field_node(node, field_name):
                return ast.unparse(node.annotation)
        msg = f"Field {field_name!r} not found in class {class_node.name!r}"
        raise ValueError(msg)

    @staticmethod
    def _has_field(class_node: ast.ClassDef, field_name: str) -> bool:
        """Check whether a class AST node contains a field with the given name."""
        return any(
            GAPICustomizer._is_field_node(node, field_name) for node in class_node.body
        )
