"""
Loads bot configuration from YAML files.
By default, this simply loads the default
configuration located at `config-default.yml`.
If a file called `config.yml` is found in the
project directory, the default configuration
is recursively updated with any settings from
the custom configuration. Any settings left
out in the custom user configuration will stay
their default values from `config-default.yml`.
"""

import logging
import os
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Dict, List

import yaml
from yaml.constructor import ConstructorError

log = logging.getLogger(__name__)


def _required_env_var_constructor(loader, node):
    """
    Implements a custom YAML tag for loading required environment
    variables. If the environment variable is set, this function
    will simply return it. Otherwise, a `CRITICAL` log message is
    given and the `KeyError` is re-raised.

    Example usage in the YAML configuration:

        bot:
            token: !REQUIRED_ENV 'BOT_TOKEN'
    """

    value = loader.construct_scalar(node)

    try:
        return os.environ[value]
    except KeyError:
        log.critical(
            f"Environment variable `{value}` is required, but was not set. "
            "Set it in your environment or override the option using it in your `config.yml`."
        )
        raise


def _env_var_constructor(loader, node):
    """
    Implements a custom YAML tag for loading optional environment
    variables. If the environment variable is set, returns the
    value of it. Otherwise, returns `None`.

    Example usage in the YAML configuration:

        # Optional app configuration. Set `MY_APP_KEY` in the environment to use it.
        application:
            key: !ENV 'MY_APP_KEY'
    """

    default = None

    try:
        # Try to construct a list from this YAML node
        value = loader.construct_sequence(node)

        if len(value) >= 2:
            # If we have at least two values, then we have both a key and a default value
            default = value[1]
            key = value[0]
        else:
            # Otherwise, we just have a key
            key = value[0]
    except ConstructorError:
        # This YAML node is a plain value rather than a list, so we just have a key
        value = loader.construct_scalar(node)

        key = str(value)

    return os.getenv(key, default)


def _join_var_constructor(loader, node):
    """
    Implements a custom YAML tag for concatenating other tags in
    the document to strings. This allows for a much more DRY configuration
    file.
    """

    fields = loader.construct_sequence(node)
    return "".join(str(x) for x in fields)


yaml.SafeLoader.add_constructor("!ENV", _env_var_constructor)
yaml.SafeLoader.add_constructor("!JOIN", _join_var_constructor)
yaml.SafeLoader.add_constructor("!REQUIRED_ENV", _required_env_var_constructor)


with open("config-default.yml", encoding="UTF-8") as f:
    _CONFIG_YAML = yaml.safe_load(f)


def _recursive_update(original, new):
    """
    Helper method which implements a recursive `dict.update`
    method, used for updating the original configuration with
    configuration specified by the user.
    """

    for key, value in original.items():
        if key not in new:
            continue

        if isinstance(value, Mapping):
            if not any(isinstance(subvalue, Mapping) for subvalue in value.values()):
                original[key].update(new[key])
            _recursive_update(original[key], new[key])
        else:
            original[key] = new[key]


if Path("config.yml").exists():
    log.info("Found `config.yml` file, loading constants from it.")
    with open("config.yml", encoding="UTF-8") as f:
        user_config = yaml.safe_load(f)
    _recursive_update(_CONFIG_YAML, user_config)


class YAMLGetter(type):
    """
    Implements a custom metaclass used for accessing
    configuration data by simply accessing class attributes.
    Supports getting configuration from up to two levels
    of nested configuration through `section` and `subsection`.

    `section` specifies the YAML configuration section (or "key")
    in which the configuration lives, and must be set.

    `subsection` is an optional attribute specifying the section
    within the section from which configuration should be loaded.

    Example Usage:

        # config.yml
        bot:
            prefixes:
                direct_message: ''
                guild: '!'

        # config.py
        class Prefixes(metaclass=YAMLGetter):
            section = "bot"
            subsection = "prefixes"

        # Usage in Python code
        from config import Prefixes
        def get_prefix(bot, message):
            if isinstance(message.channel, PrivateChannel):
                return Prefixes.direct_message
            return Prefixes.guild
    """

    subsection = None

    def __getattr__(cls, name):
        name = name.lower()

        try:
            if cls.subsection is not None:
                return _CONFIG_YAML[cls.section][cls.subsection][name]
            return _CONFIG_YAML[cls.section][name]
        except KeyError:
            dotted_path = '.'.join(
                (cls.section, cls.subsection, name)
                if cls.subsection is not None else (cls.section, name)
            )
            log.critical(f"Tried accessing configuration variable at `{dotted_path}`, but it could not be found.")
            raise

    def __getitem__(cls, name):
        return cls.__getattr__(name)


# Dataclasses
class Bot(metaclass=YAMLGetter):
    section = "bot"

    help_prefix: str
    token: str
    aoc_session_cookie: str


class Filter(metaclass=YAMLGetter):
    section = "filter"

    filter_zalgo: bool
    filter_invites: bool
    filter_domains: bool
    watch_words: bool
    watch_tokens: bool

    ping_everyone: bool
    guild_invite_whitelist: List[int]
    domain_blacklist: List[str]
    word_watchlist: List[str]
    token_watchlist: List[str]

    channel_whitelist: List[int]
    role_whitelist: List[int]


class Cooldowns(metaclass=YAMLGetter):
    section = "bot"
    subsection = "cooldowns"

    tags: int


class Colours(metaclass=YAMLGetter):
    section = "style"
    subsection = "colours"

    soft_red: int
    soft_green: int
    soft_orange: int


class Emojis(metaclass=YAMLGetter):
    section = "style"
    subsection = "emojis"

    defcon_disabled: str  # noqa: E704
    defcon_enabled: str  # noqa: E704
    defcon_updated: str  # noqa: E704

    green_chevron: str
    red_chevron: str
    white_chevron: str
    lemoneye2: str

    status_online: str
    status_offline: str
    status_idle: str
    status_dnd: str

    bullet: str
    new: str
    pencil: str
    cross_mark: str

    star: str
    christmastree: str


class Icons(metaclass=YAMLGetter):
    section = "style"
    subsection = "icons"

    crown_blurple: str
    crown_green: str
    crown_red: str

    defcon_denied: str    # noqa: E704
    defcon_disabled: str  # noqa: E704
    defcon_enabled: str   # noqa: E704
    defcon_updated: str   # noqa: E704

    filtering: str

    guild_update: str

    hash_blurple: str
    hash_green: str
    hash_red: str

    message_bulk_delete: str
    message_delete: str
    message_edit: str

    sign_in: str
    sign_out: str

    token_removed: str

    user_ban: str
    user_unban: str
    user_update: str

    user_mute: str
    user_unmute: str

    pencil: str

    remind_blurple: str
    remind_green: str
    remind_red: str


class CleanMessages(metaclass=YAMLGetter):
    section = "bot"
    subsection = "clean"

    message_limit: int


class Channels(metaclass=YAMLGetter):
    section = "guild"
    subsection = "channels"

    admins: int
    announcements: int
    big_brother_logs: int
    bot: int
    checkpoint_test: int
    devalerts: int
    devlog: int
    devtest: int
    help_0: int
    help_1: int
    help_2: int
    help_3: int
    help_4: int
    help_5: int
    helpers: int
    message_log: int
    mod_alerts: int
    modlog: int
    off_topic_1: int
    off_topic_2: int
    off_topic_3: int
    python: int
    reddit: int
    verification: int


class Roles(metaclass=YAMLGetter):
    section = "guild"
    subsection = "roles"

    admin: int
    announcements: int
    champion: int
    contributor: int
    developer: int
    devops: int
    jammer: int
    moderator: int
    muted: int
    owner: int
    verified: int
    helpers: int


class Guild(metaclass=YAMLGetter):
    section = "guild"

    id: int
    ignored: List[int]


class Keys(metaclass=YAMLGetter):
    section = "keys"

    deploy_bot: str
    deploy_site: str
    omdb: str
    site_api: str
    youtube: str


class RabbitMQ(metaclass=YAMLGetter):
    section = "rabbitmq"

    host: str
    password: str
    port: int
    username: str


class URLs(metaclass=YAMLGetter):
    section = "urls"

    # Discord API endpoints
    discord_api: str
    discord_invite_api: str

    # Misc endpoints
    bot_avatar: str
    deploy: str
    gitlab_bot_repo: str
    omdb: str
    status: str

    # Site endpoints
    site: str
    site_api: str
    site_facts_api: str
    site_clean_api: str
    site_hiphopify_api: str
    site_idioms_api: str
    site_logs_api: str
    site_logs_view: str
    site_names_api: str
    site_quiz_api: str
    site_reminders_api: str
    site_reminders_user_api: str
    site_schema: str
    site_settings_api: str
    site_special_api: str
    site_tags_api: str
    site_user_api: str
    site_user_complete_api: str
    site_infractions: str
    site_infractions_user: str
    site_infractions_type: str
    site_infractions_by_id: str
    site_infractions_user_type_current: str
    site_infractions_user_type: str
    paste_service: str


class Reddit(metaclass=YAMLGetter):
    section = "reddit"

    request_delay: int
    subreddits: list


class Wolfram(metaclass=YAMLGetter):
    section = "wolfram"

    user_limit_day: int
    guild_limit_day: int
    key: str


class AntiSpam(metaclass=YAMLGetter):
    section = 'anti_spam'

    clean_offending: bool
    ping_everyone: bool

    punishment: Dict[str, Dict[str, int]]
    rules: Dict[str, Dict[str, int]]


# Debug mode
DEBUG_MODE = True if 'local' in os.environ.get("SITE_URL", "local") else False

# Paths
BOT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BOT_DIR, os.pardir))

# Bot replies
NEGATIVE_REPLIES = [
    "Noooooo!!",
    "Nope.",
    "I'm sorry Dave, I'm afraid I can't do that.",
    "I don't think so.",
    "Not gonna happen.",
    "Out of the question.",
    "Huh? No.",
    "Nah.",
    "Naw.",
    "Not likely.",
    "No way, José.",
    "Not in a million years.",
    "Fat chance.",
    "Certainly not.",
    "NEGATORY."
]

POSITIVE_REPLIES = [
    "Yep.",
    "Absolutely!",
    "Can do!",
    "Affirmative!",
    "Yeah okay.",
    "Sure.",
    "Sure thing!",
    "You're the boss!",
    "Okay.",
    "No problem.",
    "I got you.",
    "Alright.",
    "You got it!",
    "ROGER THAT",
    "Of course!",
    "Aye aye, cap'n!",
    "I'll allow it."
]

ERROR_REPLIES = [
    "Please don't do that.",
    "You have to stop.",
    "Do you mind?",
    "In the future, don't do that.",
    "That was a mistake.",
    "You blew it.",
    "You're bad at computers.",
    "Are you trying to kill me?",
    "Noooooo!!"
]


class Event(Enum):
    """
    Event names. This does not include every event (for example, raw
    events aren't here), but only events used in ModLog for now.
    """

    guild_channel_create = "guild_channel_create"
    guild_channel_delete = "guild_channel_delete"
    guild_channel_update = "guild_channel_update"
    guild_role_create = "guild_role_create"
    guild_role_delete = "guild_role_delete"
    guild_role_update = "guild_role_update"
    guild_update = "guild_update"

    member_join = "member_join"
    member_remove = "member_remove"
    member_ban = "member_ban"
    member_unban = "member_unban"
    member_update = "member_update"

    message_delete = "message_delete"
    message_edit = "message_edit"
