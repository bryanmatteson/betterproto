from typing import Any, Dict, Literal

from pydantic import BaseModel


class PluginOptions(BaseModel):
    mode: Literal["sync", "async"] = "sync"
    include_google: bool = False

    @classmethod
    def parse_args(cls, args: str) -> "PluginOptions":
        all_options = [x.lower() for x in args.split(",")]
        options: Dict[str, Any] = {}
        for option in all_options:
            if "=" in option:
                key, value = option.split("=", 1)
                options[key] = value
            else:
                options[option] = True
        return cls(**options)
