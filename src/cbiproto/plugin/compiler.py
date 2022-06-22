import os.path
import textwrap

try:
    # cbiproto[compiler] specific dependencies
    import black
    import isort.api
    import jinja2
except ImportError as err:
    print(
        "\033[31m"
        f"Unable to import `{err.name}` from cbiproto plugin! "
        "Please ensure that you've installed cbiproto as "
        '`pip install "cbiproto[compiler]"` so that compiler dependencies '
        "are included."
        "\033[0m"
    )
    raise SystemExit(1)

from .models import OutputTemplate


def with_header(code: str) -> str:
    header = textwrap.dedent(
        """
        # Generated by the protocol buffer compiler.  DO NOT EDIT!
        # type: ignore
        # flake8: noqa
        # nopycln: file
        # pyright: ignore
        # mypy: ignore-errors
        # fmt: off
        """
    ).lstrip()
    return header + code


def outputfile_compiler(output_file: OutputTemplate) -> str:
    templates_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates"))
    env = jinja2.Environment(
        trim_blocks=True,
        lstrip_blocks=True,
        loader=jinja2.FileSystemLoader(templates_folder),
    )
    template = env.get_template("template.py.j2")

    code = template.render(output_file=output_file)
    code = isort.api.sort_code_string(
        code=code,
        show_diff=False,
        py_version=37,
        profile="black",
        combine_as_imports=True,
        lines_after_imports=2,
        quiet=True,
        force_grid_wrap=2,
        known_third_party=["grpclib", "cbiproto"],
    )
    return with_header(black.format_str(code, mode=black.FileMode(line_length=120)))
