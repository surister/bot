import logging
from typing import Callable
from typing import Dict

from discord import Colour, Embed
from discord.ext.commands import Bot, Context, command

from bot.constants import Gitlab as GitlabConfig
from bot.constants import Roles
from bot.decorators import with_role
from bot.pagination import LinePaginator
from bot.utils import CaseInsensitiveDict

GITLAB_ICON = "https://img.crx4chrome.com/fc/7b/cf/kfjchffabpogdehadpflljaikjicdpng-icon.png"

API_URL = "https://gitlab.com/api/v4"
GET_ISSUES_URL = API_URL + "/projects/{project_id}/issues"
GET_ISSUE_URL = GET_ISSUES_URL + "/{issue_id}"
GET_PROJECTS_URL = API_URL + "/projects?membership=True"

HEADERS = {
    "Private-Token": GitlabConfig.key,
    "Content-Type": "application/json"
}

log = logging.getLogger(__name__)


class GitlabException(Exception):

    def __init__(self, message) -> None:
        super().__init__(message)
        self.message = message


class Gitlab:
    """
    gitlab management commands
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.projects = CaseInsensitiveDict()

    async def _request(self, method: Callable, url: str, headers: Dict[str, str] = HEADERS, json: Dict = None,
                       **kwargs):
        response = await method(url, headers=headers, json=json, **kwargs)
        result = await response.json()

        if 200 <= response.status < 300:
            return result
        else:
            log.error(f"Failed to {method.__name__} {url}: `{response.status}`: {result}")
            raise GitlabException(result)

    async def get(self, url: str, headers: Dict[str, str] = HEADERS, **queryparams):
        return await self._request(self.bot.http_session.get, url, headers=headers, params=queryparams)

    async def post(self, url: str, headers: Dict[str, str] = HEADERS, data: Dict = None):
        return await self._request(self.bot.http_session.post, url, headers=headers, json=data)

    async def on_ready(self):
        projects = await self.get(GET_PROJECTS_URL)
        self.projects = {project['id']: project['name'] for project in projects}

    def get_project(self, name_or_id: str):
        return next(((project_id, name)
                     for project_id, name in self.projects.items()
                     if name == name_or_id or project_id == name_or_id),
                    (None, None))

    async def fail(self, ctx: Context, message: str, embed: Embed = None):
        embed = embed or Embed(colour=Colour.blurple())
        embed.description = message
        embed.colour = Colour.red()
        return await ctx.send(embed=embed)

    def _create_issue_embed(self, project_name: str, issue: Dict):
        embed = Embed(colour=Colour.blurple())
        embed.set_author(name=f"Gitlab |project {project_name}| - issue {issue['iid']}: {issue['title']}",
                         icon_url=GITLAB_ICON,
                         url=issue['web_url'])
        embed.add_field(name="Author",
                        value=f"[{issue['author']['name']}]({issue['author']['web_url']})",
                        inline=False)
        if issue['description']:
            embed.add_field(name=f"Description",
                            value=f"{issue['description'][:1024]}",
                            inline=False)
        embed.add_field(name="State",
                        value=issue['state'])
        if issue['labels']:
            embed.add_field(name="Labels",
                            value=', '.join(issue['labels']))
        if issue['assignee']:
            embed.add_field(name="Assignee",
                            value=f"[{issue['assignee']['name']}]({issue['assignee']['web_url']})")
        else:
            embed.add_field(name="Assignee",
                            value="No-one")
        return embed

    @command(name="gitlab.projects()", aliases=["gitlab.projects", "projects", "get_projects"])
    @with_role(Roles.moderator, Roles.admin, Roles.owner, Roles.devops, Roles.contributor)
    async def get_projects(self, ctx: Context):
        """Get all the projects"""
        try:
            projects = await self.get(GET_PROJECTS_URL)
            # Might as well udpate the little cache
            self.projects = {project['id']: project['name'] for project in projects}
        except GitlabException as e:
            return await self.fail(ctx, e.message)

        log.debug(f"{ctx.author} requested a list of all Gitlab projects. Preparing the list...")
        embed = Embed(colour=Colour.blurple())

        for i in range(0, len(projects), 10):
            embed.add_field(name=f'Projects {1+i}-{min(i+10, len(projects))}',
                            value='\n'.join(f"`{project['id']}`: {project['name']} "
                                            f"([link]({project['http_url_to_repo']}))"
                                            for project in projects[i: i + 10]))

        embed.set_author(name="Gitlab Projects",
                         icon_url=GITLAB_ICON,
                         url=f"https://gitlab.com/dashboard/projects")

        log.debug(f"List fully prepared, returning list to channel.")
        await ctx.send(embed=embed)

    @command(name="gitlab.issues()", aliases=["gitlab.issues", "issues", "get_issues"])
    @with_role(Roles.moderator, Roles.admin, Roles.owner, Roles.devops, Roles.contributor)
    async def get_issues(self, ctx: Context, project: str, state: str = 'opened', labels: str = None):
        """
        Get a list of issues per project, optionally with a specific status or label.

        project (required) can be the name or id of a project.
        status (optional) can be 'opened' or 'closed'.
        labels (optional) is a comma-seperated string of labels to match with.
        """
        project_id, project_name = self.get_project(project)
        if project_id is None:
            log.warning(f"{ctx.author} requested '{project}', but that project is unknown. Rejecting request.")
            return await self.fail(ctx, f"Unknown project: {project}")

        embed = Embed(colour=Colour.blurple())
        embed.set_author(name=f"Gitlab issues for project {project_name}",
                         icon_url=GITLAB_ICON,
                         url=f"https://gitlab.com/python-discord/projects/{project_id}/issues")

        queryparams = {'state': state}
        if labels is not None:
            queryparams['labels'] = labels
        try:
            issues = await self.get(GET_ISSUES_URL.format(project_id=project_id), **queryparams)
        except GitlabException as e:
            log.warning(f"{ctx.author} requested '{project}' issues, but an error occurred: {e.message}")
            return await self.fail(ctx, e.message, embed=embed)

        if not issues:
            log.debug(f"{ctx.author} requested a list of gitlab tasks, but no gitlab tasks were found.")
            return await self.fail(ctx, f"No issues found for project {project_name}.", embed=embed)

        lines = []
        for issue in issues:
            id_fragment = f"[`#{issue['iid']: <3}`]({issue['web_url']})"
            status = f"{issue['state'].title()}"

            lines.append(f"{id_fragment} ({status})\n\u00BB {issue['title']}")

        log.debug(f"{ctx.author} requested a list of Gitlab issues. Returning list.")
        await LinePaginator.paginate(lines, ctx, embed, max_size=750)

    @command(name="gitlab.issue()", aliases=["gitlab.issue", "issue", "get_issue"])
    @with_role(Roles.moderator, Roles.admin, Roles.owner, Roles.devops, Roles.contributor)
    async def get_issue(self, ctx: Context, project: str, issue_id: str):
        """
        Retrieves the details of an issue in a project.

        project (required) can be the name or id of a project.
        issue_id (required) is the id of the issue within the project. Also known as the iid, not id.
        """
        project_id, project_name = self.get_project(project)
        if project_id is None:
            log.warning(f"{ctx.author} requested '{project}', but that project is unknown. Rejecting request.")
            return await self.fail(ctx, f"Unknown project: {project}")
        try:
            issue = await self.get(GET_ISSUE_URL.format(project_id=project_id, issue_id=issue_id))
        except GitlabException as e:
            log.warning(f"{ctx.author} requested '{project}' issues, but an error occurred: {e.message}")
            return await self.fail(ctx, e.message)

        embed = self._create_issue_embed(project_name, issue)
        await ctx.send(embed=embed)

    @command(name="gitlab.open()", aliases=["gitlab.open", "open", "open_issue"])
    @with_role(Roles.moderator, Roles.admin, Roles.owner, Roles.devops, Roles.contributor)
    async def create_issue(self, ctx: Context, project: str, title: str):
        """
        Creates an issue within a project with the given title.

        Status will be open, and assignee will be nobody.

        project (required) can be the name or id of a project.
        title (required) is the title of the issue to be created.
        """
        project_id, project_name = self.get_project(project)
        if project_id is None:
            log.warning(f"{ctx.author} requested '{project}', but that project is unknown. Rejecting request.")
            return await self.fail(ctx, f"Unknown project: {project}")

        try:
            issue = await self.post(GET_ISSUES_URL.format(project_id=project_id),
                                    data={'title': title})
        except GitlabException as e:
            log.warning(f"Issue could not be created: {e.message}")
            return await self.fail(ctx, e.message)
        embed = self._create_issue_embed(project_name, issue)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Gitlab(bot))
    log.info("Cog loaded: Gitlab")
