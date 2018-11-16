import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands

from bot.constants import AdventOfCode as AocConfig
from bot.constants import Colours, Emojis, Roles
from bot.decorators import with_role

log = logging.getLogger(__name__)

AOC_SESSION_COOKIE = {"session": AocConfig.session_cookie}


class AdventOfCode:
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.leaderboard_link = (
            f"https://adventofcode.com/{AocConfig.year}/leaderboard/private/view/" f"{AocConfig.leaderboard_id}"
        )
        self.cached_leaderboard = None

        self.about_aoc_filepath = Path("./bot/resources/advent_of_code/about.txt")
        self._cached_about_aoc = self._cache_info()

    @commands.group(name="adventofcode", aliases=("aoc", "AoC", "AOC"), invoke_without_command=True)
    async def adventofcode_group(self, ctx: commands.Context):
        """
        Advent of Code festivities! Ho Ho Ho!
        """

        await ctx.invoke(self.bot.get_command("help"), "adventofcode")

    @adventofcode_group.command(name="about", aliases=("ab", "info"))
    async def about_aoc(self, ctx: commands.Context):
        """
        Respond with an explanation all things Advent of Code
        """

        await ctx.send(self._cached_about_aoc)

    @adventofcode_group.command(name="join", aliases=("j",))
    async def join_leaderboard(self, ctx: commands.Context):
        """
        Reply with the link to join the PyDis AoC private leaderboard
        """

        info_str = (
            "Head over to https://adventofcode.com/leaderboard/private "
            f"with code `{AocConfig.leaderboard_join_code}` to join the PyDis private leaderboard!"
        )
        await ctx.send(info_str)

    @adventofcode_group.command(name="reauthenticate", aliases=("auth",))
    @with_role(Roles.owner, Roles.admin)
    async def reauthenticate(self, ctx: commands.Context):
        """
        Helper method to reload authentication from its environmental variable in the event
        of login expiration
        """

        global AOC_SESSION_COOKIE
        _author = ctx.message.author
        log.info(f"AoC session cookie update forced by {_author.name} ({_author.id})")
        try:
            AOC_SESSION_COOKIE = {"session": os.environ["AOC_SESSION_COOKIE"]}
        except KeyError:
            log.warning("AoC session key environment variable is not set")
            ctx.send("AoC session key environment variable is not set")

    @adventofcode_group.command(name="leaderboard", aliases=("board", "stats"))
    async def aoc_leaderboard(self, ctx: commands.Context, n_disp: int = 10):
        """
        Pull the top n_disp members from the PyDis leaderboard and post an embed

        For readability, n_disp is capped at 10. Responses greater than this limit
        (or less than 1) will default to 10 prompt a direct link to the leaderboard.
        """

        if not self.cached_leaderboard:
            await ctx.send(
                "Something's gone wrong and there's no cached leaderboard!\n\nPlease check in with a staff member."
            )
            return

        # Check for n > max_entries and n <= 0
        max_entries = 10
        _author = ctx.message.author
        if not 0 <= n_disp <= max_entries:
            log.debug(
                f"{_author.name} ({_author.id}) attempted to fetch an invalid number "
                f" of entries from the AoC leaderboard ({n_disp})"
            )
            await ctx.send(
                f"{_author.mention}, number of entries to display must be a positive "
                f"integer less than or equal to {max_entries}\n\n"
                f"Head to {self.leaderboard_link} to view the entire leaderboard"
            )
            n_disp = max_entries

        # Generate leaderboard table for embed
        members_to_print = self.cached_leaderboard.top_n(n_disp)
        stargroup = f"{Emojis.star}, {Emojis.star*2}"
        header = f"{' '*3}{'Score'} {'Name':^25} {stargroup:^7}\n{'-'*44}"
        table = ""
        for i, member in enumerate(members_to_print):
            if member.name == "Anonymous User":
                name = f"{member.name} #{member.aoc_id}"
            else:
                name = member.name

            table += (
                f"{i+1:2}) {member.local_score:4} {name:25.25} "
                f"({member.completions[0]:2}, {member.completions[1]:2})\n"
            )
        else:
            table = f"```{header}\n{table}```"

        # Build embed
        aoc_embed = discord.Embed(colour=Colours.soft_green, timestamp=self.cached_leaderboard.last_updated)
        aoc_embed.set_author(name="Advent of Code", url=self.leaderboard_link)
        aoc_embed.set_footer(text="Last Updated")

        await ctx.send(
            content=f"Here's the current Top {n_disp}! {Emojis.christmas_tree*3}\n\n{table}", embed=aoc_embed
        )

    async def aoc_update_loop(self, seconds_to_sleep: int = 3600):
        """
        Async timer to update AoC leaderboard
        """

        while True:
            raw_json = await AocLeaderboard.json_from_url()
            if self.cached_leaderboard:
                self.cached_leaderboard._update(raw_json)
            else:
                # Leaderboard hasn't been cached yet
                log.debug("No cached AoC leaderboard found")
                self.cached_leaderboard = AocLeaderboard.from_json(raw_json)

            await asyncio.sleep(seconds_to_sleep)

    async def _cache_info(self):
        """
        Load Advent of Code's about.txt & cache for command use
        """
        with self.about_aoc_filepath.open("r") as f:
            self._cached_about_aoc = f.read()


class AocLeaderboard:
    def __init__(self, members: list, owner_id: int, event_year: int):
        self.members = members
        self._owner_id = owner_id
        self._event_year = event_year
        self.last_updated = datetime.utcnow()

    def _update(self, injson: dict):
        """
        From AoC's private leaderboard API JSON, update members & resort
        """

        log.debug("Updating cached Advent of Code Leaderboard")
        self.members = AocLeaderboard._sorted_members(injson["members"])

    def top_n(self, n: int = 10) -> dict:
        """
        Return the top n participants on the leaderboard.

        If n is not specified, default to the top 10
        """

        return self.members[:n]

    @staticmethod
    async def json_from_url(
        leaderboard_id: int = AocConfig.leaderboard_id, year: int = AocConfig.year
    ) -> "AocLeaderboard":
        """
        Request the API JSON from Advent of Code for leaderboard_id for the specified year's event

        If no year is input, year defaults to the current year
        """

        api_url = f"https://adventofcode.com/{year}/leaderboard/private/view/{leaderboard_id}.json"

        log.debug("Querying Advent of Code Private Leaderboard API")
        headers = {"user-agent": "PythonDiscord AoC Event Bot"}
        async with aiohttp.ClientSession(cookies=AOC_SESSION_COOKIE, headers=headers) as session:
            async with session.get(api_url) as resp:
                if resp.status == 200:
                    raw_dict = await resp.json()
                else:
                    log.warning(f"Bad response received from AoC ({resp.status}), check session cookie")
                    resp.raise_for_status()

        return raw_dict

    @classmethod
    def from_json(cls, injson: dict) -> "AocLeaderboard":
        """
        Generate an AocLeaderboard object from AoC's private leaderboard API JSON
        """

        return cls(
            members=cls._sorted_members(injson["members"]), owner_id=injson["owner_id"], event_year=injson["event"]
        )

    @staticmethod
    def _sorted_members(injson: dict) -> list:
        """
        Generate a sorted list of AocMember objects from AoC's private leaderboard API JSON

        Output list is sorted based on the AocMember.local_score
        """

        members = [AocMember.member_from_json(injson[member]) for member in injson]
        members.sort(key=lambda x: x.local_score, reverse=True)

        return members


class AocMember:
    def __init__(self, name: str, aoc_id: int, stars: int, starboard: list, local_score: int, global_score: int):
        self.name = name
        self.aoc_id = aoc_id
        self.stars = stars
        self.starboard = starboard
        self.local_score = local_score
        self.global_score = global_score
        self.completions = self._completions_from_starboard(self.starboard)

    def __repr__(self):
        return f"<{self.name} ({self.aoc_id}): {self.local_score}>"

    @classmethod
    def member_from_json(cls, injson: dict) -> "AocMember":
        """
        Generate an AocMember from AoC's private leaderboard API JSON

        injson is expected to be the dict contained in:

            AoC_APIjson['members'][<member id>:str]

        Returns an AocMember object
        """

        return cls(
            name=injson["name"] if injson["name"] else "Anonymous User",
            aoc_id=int(injson["id"]),
            stars=injson["stars"],
            starboard=cls._starboard_from_json(injson["completion_day_level"]),
            local_score=injson["local_score"],
            global_score=injson["global_score"],
        )

    @staticmethod
    def _starboard_from_json(injson: dict) -> list:
        """
        Generate starboard from AoC's private leaderboard API JSON

        injson is expected to be the dict contained in:

            AoC_APIjson['members'][<member id>:str]['completion_day_level']

        Returns a list of 25 lists, where each nested list contains a pair of booleans representing
        the code challenge completion status for that day
        """

        # Basic input validation
        if not isinstance(injson, dict):
            raise ValueError

        # Initialize starboard
        starboard = []
        for _i in range(25):
            starboard.append([False, False])

        # Iterate over days, which are the keys of injson (as str)
        for day in injson:
            idx = int(day) - 1
            # If there is a second star, the first star must be completed
            if "2" in injson[day].keys():
                starboard[idx] = [True, True]
            # If the day exists in injson, then at least the first star is completed
            else:
                starboard[idx] = [True, False]

        return starboard

    @staticmethod
    def _completions_from_starboard(starboard: list) -> tuple:
        """
        Return days completed, as a (1 star, 2 star) tuple, from starboard
        """

        completions = [0, 0]
        for day in starboard:
            if day[0]:
                completions[0] += 1
            if day[1]:
                completions[1] += 1

        return tuple(completions)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(AdventOfCode(bot))
    log.info("Cog loaded: adventofcode")
