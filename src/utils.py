# coding: utf-8

# Author: Du Mingzhe (mingzhe@nus.edu.sg)
# Date: 2025-06-06

import json
import jinja2
import requests
import textwrap
from typing import Any

def render_template(template_path: str, **kwargs) -> str:
    with open(template_path, 'r') as f:
        template = jinja2.Template(f.read())
    return template.render(**kwargs)