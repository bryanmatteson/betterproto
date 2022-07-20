import keyword
import re

# Word delimiters and symbols that will not be preserved when re-casing.
_SYMBOLS = "[^a-zA-Z0-9]*"

# Optionally capitalized word.
_WORD = "[A-Z]*[a-z]*[0-9]*"

# Uppercase word, not followed by lowercase letters.
_WORD_UPPER = "[A-Z]+(?![a-z])[0-9]*"


def safe_snake_case(value: str) -> str:
    value = snake_case(value)
    value = sanitize_name(value)
    return value


def snake_case(value: str, strict: bool = True) -> str:
    def substitute_word(symbols: str, word: str, is_start: bool) -> str:
        if not word:
            return ""
        if strict:
            delimiter_count = 0 if is_start else 1  # Single underscore if strict.
        elif is_start:
            delimiter_count = len(symbols)
        elif word.isupper() or word.islower():
            delimiter_count = max(1, len(symbols))  # Preserve all delimiters if not strict.
        else:
            delimiter_count = len(symbols) + 1  # Extra underscore for leading capital.

        return ("_" * delimiter_count) + word.lower()

    snake = re.sub(
        f"(^)?({_SYMBOLS})({_WORD_UPPER}|{_WORD})",
        lambda groups: substitute_word(groups[2], groups[3], groups[1] is not None),
        value,
    )
    return snake


def pascal_case(value: str, strict: bool = True) -> str:
    def substitute_word(symbols, word):
        if strict:
            return word.capitalize()  # Remove all delimiters

        if word.islower():
            delimiter_length = len(symbols[:-1])  # Lose one delimiter
        else:
            delimiter_length = len(symbols)  # Preserve all delimiters

        return ("_" * delimiter_length) + word.capitalize()

    return re.sub(f"({_SYMBOLS})({_WORD_UPPER}|{_WORD})", lambda groups: substitute_word(groups[1], groups[2]), value,)


def camel_case(value: str, strict: bool = True) -> str:
    return lowercase_first(pascal_case(value, strict=strict))


def lowercase_first(value: str) -> str:
    return value[0:1].lower() + value[1:]


def sanitize_name(value: str) -> str:
    return f"{value}_" if keyword.iskeyword(value) else value
