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
        new_field: The new field definition as a string, e.g. ``"field_name: int"``.
    """

    class_name: str
    field_name: str
    new_field: str

    def generate_field_ast(self) -> list[ast.stmt]:
        """Generate the replacement field as a list of AST statement nodes."""
        return ast.parse(self.new_field).body


@dataclass
class CustomSerializer:
    """Custom serializers to be used with GAPICustomizer.

    Attributes:
        field_name: The name of the field to serialize.
        serializer_code: The serializer body as a string or list of lines.
        input_type: Type annotation for the ``value`` parameter.
        output_type: The return type annotation.
        class_name: The class to add the serializer to. If None, applies to all
            classes with the matching field.
    """

    field_name: str
    serializer_code: str | list[str]
    input_type: str = field(kw_only=True)
    output_type: str = field(kw_only=True)
    class_name: str | None = field(default=None, kw_only=True)

    def create_serializer_ast(self) -> list[ast.stmt]:
        """Generate the ``@field_serializer`` decorated method as AST nodes.

        Returns:
            The serializer method as a list of AST statement nodes.
        """
        serializer_code = self.serializer_code
        if isinstance(serializer_code, str):
            serializer_code = serializer_code.split("\n")

        source = (
            f'@field_serializer("{self.field_name}")\n'
            f"def serialize_{self.field_name}"
            f"(self, value: {self.input_type})"
            f" -> {self.output_type}:\n"
            "    "
            f"{'\n    '.join(serializer_code)}"
        )
        return ast.parse(source).body


class GAPICustomizer:
    """Compiles and applies customizations to generated models."""

    def __init__(self) -> None:
        """Initialize GAPICustomizer."""
        self.replacement_fields: list[ReplacementField] = []
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
            new_field: The new field definition, e.g. ``"my_field: int"``.
        """
        replacement_field = ReplacementField(
            class_name=class_name,
            field_name=field_name,
            new_field=new_field,
        )
        self.replacement_fields.append(replacement_field)

    def add_custom_serializer(
        self,
        field_name: str,
        serializer_code: str | list[str],
        input_type: str,
        output_type: str,
        class_name: str | None = None,
    ) -> None:
        """Add a custom serializer to apply during model generation.

        Args:
            field_name: The field to add the serializer to.
            serializer_code: The serializer body as a string or list of lines.
                Indentation is not required.
            class_name: The class to add the serializer to. If None, applies to
                all classes with the matching field.
            input_type: Type annotation for the ``value`` parameter.
            output_type: Return type annotation for the serializer.
        """
        custom_serializer = CustomSerializer(
            class_name=class_name,
            field_name=field_name,
            serializer_code=serializer_code,
            input_type=input_type,
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
        self._apply_replacement_fields(class_nodes)
        self._apply_custom_serializers(class_nodes)

        additional_imports = list(self.additional_imports)
        if self.custom_serializers:
            additional_imports.append("from pydantic import field_serializer")
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

    def _apply_custom_serializers(self, class_nodes: dict[str, ast.ClassDef]) -> None:
        """Insert serializer methods into class bodies."""
        if not self.custom_serializers:
            return

        for custom_serializer in self.custom_serializers:
            serializer_ast = custom_serializer.create_serializer_ast()
            # If a class_name is defined only add the serializer to that class.
            if class_name := custom_serializer.class_name:
                if class_name not in class_nodes:
                    msg = f"Class {class_name!r} not found in generated models"
                    raise ValueError(msg)
                class_nodes[class_name].body.extend(serializer_ast)
            # If a class_name is not defined add the serializer to all classes that have
            # a matching field name.
            else:
                for class_node in class_nodes.values():
                    if self._has_field(class_node, custom_serializer.field_name):
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
    def _has_field(class_node: ast.ClassDef, field_name: str) -> bool:
        """Check whether a class AST node contains a field with the given name."""
        return any(
            GAPICustomizer._is_field_node(node, field_name) for node in class_node.body
        )
