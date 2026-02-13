import os
import re
import json
import sys
import locale
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI