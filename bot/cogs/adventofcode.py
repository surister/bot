import typing


class AocLeaderboard:
    def __init__(self, members: typing.List, owner_id: int, event_year: int):
        self.members = members
        self._owner_id = owner_id
        self._event_year = event_year
        self._ranking = None

    def _update(self, injson: typing.Dict):
        """
        Update members & recalculate _ranking
        """
        raise NotImplementedError

    def _top5(self) -> typing.Dict:
        """
        Return the top 5 participants on the leaderboard
        """
        raise NotImplementedError

    @staticmethod
    def _new_from_json(injson: typing.Dict) -> "AocLeaderboard":
        """
        Generate an AocLeaderboard object from AoC's private leaderboard API JSON
        """
        return AocLeaderboard(
            members=[
                AocMember._member_from_json(injson["members"][member])
                for member in injson["members"]
            ],
            owner_id=injson["owner_id"],
            event_year=injson["event"],
        )


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

    @staticmethod
    def _member_from_json(injson: typing.Dict) -> "AocMember":
        """
        Generate an AocMember from AoC's private leaderboard API JSON
        
        injson is expected to be the dict contained in:
        
            AoC_APIjson['members'][<member id>:str]
            
        Returns an AocMember object
        """
        return AocMember(
            name=injson["name"],
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
        for i in range(25):
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
