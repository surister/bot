import asyncio
import logging
import typing
from datetime import datetime

import aiohttp
from discord.ext import commands

from bot.constants import Roles
from bot.decorators import with_role

log = logging.getLogger(__name__)


class AdventOfCode:
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.cached_leaderboard = None

    @commands.group(
        name="adventofcode",
        aliases=("AoC",),
        invoke_without_command=True,
        case_insensitive=True,
    )
    async def adventofcode_group(self, ctx: commands.Context):
        """
        Advent of Code festivities! Ho Ho Ho!
        """
        await ctx.invoke(self.bot.get_command("help"), "adventofcode")

    @adventofcode_group.command(name="about", aliases=("ab",))
    async def about_aoc(self, ctx: commands.Context):
        """
        Display an embed explaining all things Advent of Code
        """
        raise NotImplementedError

    @adventofcode_group.command(name="join", aliases=("j",))
    async def join_leaderboard(self, ctx: commands.Context):
        """
        Reply with the link to join the PyDis AoC private leaderboard
        """
        raise NotImplementedError

    @adventofcode_group.command(name="reauthenticate", aliases=("auth",))
    @with_role(Roles.owner, Roles.admin)
    async def reauthenticate(self, ctx: commands.Context):
        """
        Helper method to reload authentication from its environmental variable in the event
        of login expiration
        """
        raise NotImplementedError

    @adventofcode_group.command(name="leaderboard", aliases=("board", "stats"))
    async def aoc_leaderboard(self, ctx: commands.Context, n_disp: int = 10):
        """
        Pull the top n_disp members from the PyDis leaderboard and post an embed
        """
        raise NotImplementedError

    async def aoc_update_loop(self, seconds_to_sleep: int = 3600):
        """
        Async timer to update AoC leaderboard
        """
        while True:
            if self.cached_leaderboard:
                self.cached_leaderboard._update()
            else:
                # Leaderboard hasn't been cached yet
                log.info("No cached AoC leaderboard found")
                self.cached_leaderboard = await AocLeaderboard._from_url()

            asyncio.sleep(seconds_to_sleep)


class AocLeaderboard:
    def __init__(self, members: typing.List, owner_id: int, event_year: int):
        self.members = members
        self._owner_id = owner_id
        self._event_year = event_year

    def _update(self, injson: typing.Dict):
        """
        From AoC's private leaderboard API JSON, update members & resort
        """
        log.info("Updating cached Advent of Code Leaderboard")
        self.members = AocLeaderboard._sorted_members(injson["members"])

    def _top_n(self, n: int = 5) -> typing.Dict:
        """
        Return the top 5 participants on the leaderboard
        """
        return self.members[:n]

    @staticmethod
    async def _from_url(
        leaderboard_id: int = 363_275, year: int = datetime.today().year
    ) -> "AocLeaderboard":
        """
        Request the API JSON from Advent of Code for leaderboard_id for the specified year's event

        If no year is input, year defaults to the current year
        """
        api_url = f"https://adventofcode.com/{year}/leaderboard/private/view/{leaderboard_id}.json"

        # TODO: Add headers, authentication (need Volcyy to get & store cookie to env)
        # TODO: Add handling for denied request
        log.debug("Querying Advent of Code Private Leaderboard API")
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                rawdict = await resp.json()

        return AocLeaderboard._new_from_json(rawdict)

    @staticmethod
    def _new_from_json(injson: typing.Dict) -> "AocLeaderboard":
        """
        Generate an AocLeaderboard object from AoC's private leaderboard API JSON
        """
        return AocLeaderboard(
            members=AocLeaderboard._sorted_members(injson["members"]),
            owner_id=injson["owner_id"],
            event_year=injson["event"],
        )

    @staticmethod
    def _sorted_members(injson: typing.Dict) -> typing.List:
        """
        Generate a sorted list of AocMember objects from AoC's private leaderboard API JSON

        Output list is sorted based on the AocMember.local_score
        """

        members = [AocMember._member_from_json(injson[member]) for member in injson]
        members.sort(key=lambda x: x.local_score, reverse=True)

        return members


class AocMember:
    def __init__(
        self,
        name: str,
        aoc_id: int,
        stars: int,
        starboard: typing.List,
        local_score: int,
        global_score: int,
    ):
        self.name = name
        self.aoc_id = aoc_id
        self.stars = stars
        self.starboard = starboard
        self.local_score = local_score
        self.global_score = global_score

    def __repr__(self):
        return f"<{self.name} ({self.aoc_id}): {self.local_score}>"

    @staticmethod
    def _member_from_json(injson: typing.Dict) -> "AocMember":
        """
        Generate an AocMember from AoC's private leaderboard API JSON

        injson is expected to be the dict contained in:

            AoC_APIjson['members'][<member id>:str]

        Returns an AocMember object
        """
        return AocMember(
            name=injson["name"] if injson["name"] else "Anonymous User",
            aoc_id=int(injson["id"]),
            stars=injson["stars"],
            starboard=AocMember._starboard_from_json(injson["completion_day_level"]),
            local_score=injson["local_score"],
            global_score=injson["global_score"],
        )

    @staticmethod
    def _starboard_from_json(injson: typing.Dict) -> typing.List:
        """
        Generate starboard from AoC's private leaderboard API JSON

        injson is expected to be the dict contained in:

            AoC_APIjson['members'][<member id>:str]['completion_day_level']

        Returns a list of 25 lists, where each nested list contains a pair of booleans representing
        the code challenge completion status for that day
        """
        # Basic input validation
        if not isinstance(injson, dict) or injson is None:
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


def setup(bot: commands.Bot) -> None:
    bot.add_cog(AdventOfCode(bot))
    log.info("Cog loaded: adventofcode")
