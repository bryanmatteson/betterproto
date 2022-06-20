from .._utils import pascal_case, safe_snake_case


def pythonize_class_name(name: str) -> str:
    return pascal_case(name)


def pythonize_field_name(name: str) -> str:
    return safe_snake_case(name)


def pythonize_method_name(name: str) -> str:
    return safe_snake_case(name)
