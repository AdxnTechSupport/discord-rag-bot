"""Discord bot: /ask, /help, /stats slash commands with reaction-based feedback."""

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = ["DISCORD_TOKEN", "DISCORD_GUILD_ID"]
missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
if missing:
    sys.exit(f"Missing required environment variables: {', '.join(missing)}")

import discord
from discord import app_commands

from .api_client import check_health, get_stats, post_feedback, query_rag

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger(__name__)

GUILD_ID = int(os.environ["DISCORD_GUILD_ID"])
BLURPLE = 0x5865F2
RED = 0xED4245
GREEN = 0x57F287
YELLOW = 0xFEE75C

THUMBS_UP = "👍"
THUMBS_DOWN = "👎"
MAX_EMBED_DESCRIPTION = 4000


class RAGBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.reactions = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        # Maps message_id -> question text so feedback handler can reference the query
        self.tracked_messages: dict[int, str] = {}

    async def setup_hook(self) -> None:
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def on_ready(self) -> None:
        log.info("Logged in as %s | Guilds: %d", self.user, len(self.guilds))
        print(f"Bot online: {self.user} | Connected to {len(self.guilds)} guild(s)")
        try:
            health = await check_health()
            print(f"API health: status={health.get('status')} db={health.get('db')}")
            log.info("API health check passed: %s", health)
        except Exception as exc:
            print(f"API health check failed: {exc}")
            log.warning("API health check failed: %s", exc)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        # Ignore the bot's own reactions
        if payload.user_id == self.user.id:
            return

        question = self.tracked_messages.get(payload.message_id)
        if question is None:
            return

        emoji = str(payload.emoji)
        if emoji not in {THUMBS_UP, THUMBS_DOWN}:
            return

        rating = "positive" if emoji == THUMBS_UP else "negative"
        log.info(
            "Feedback reaction: message_id=%d user_id=%d rating=%s",
            payload.message_id,
            payload.user_id,
            rating,
        )
        try:
            await post_feedback(
                message_id=str(payload.message_id),
                user_id=str(payload.user_id),
                query=question,
                rating=rating,
            )
        except Exception as exc:
            log.warning("Failed to post feedback to API: %s", exc)


client = RAGBot()


@client.tree.command(
    name="ask",
    description="Ask a question about the PM Accelerator program",
)
@app_commands.describe(question="Your question about the program")
async def ask(interaction: discord.Interaction, question: str) -> None:
    await interaction.response.defer()

    # Ephemeral "thinking" message so the user sees immediate feedback
    await interaction.followup.send(
        "🔍 Searching the knowledge base...",
        ephemeral=True,
    )

    log.info("Slash /ask: user=%s question=%r", interaction.user, question)

    try:
        data = await query_rag(question)
    except Exception as exc:
        log.exception("API call failed for question %r: %s", question, exc)
        error_embed = discord.Embed(
            title="❌ Error",
            description="Something went wrong. Please try again in a moment.",
            color=RED,
        )
        await interaction.followup.send(embed=error_embed)
        return

    answer: str = data.get("answer", "No answer returned.")
    sources: list[str] = data.get("sources", [])
    chunks_used: int = data.get("chunks_used", 0)

    # Truncate to Discord's embed description limit
    truncated = False
    if len(answer) > MAX_EMBED_DESCRIPTION:
        answer = answer[:MAX_EMBED_DESCRIPTION - 40] + "\n\n*(Answer truncated due to length.)*"
        truncated = True

    embed = discord.Embed(
        title="📚 Answer",
        description=answer,
        color=BLURPLE,
    )
    footer_sources = f"Sources: {', '.join(sources)}" if sources else "No sources cited"
    embed.set_footer(text=f"{footer_sources} • {chunks_used} chunk(s) used")

    msg = await interaction.followup.send(embed=embed)

    # Add reaction buttons and track the message for feedback
    try:
        await msg.add_reaction(THUMBS_UP)
        await msg.add_reaction(THUMBS_DOWN)
        client.tracked_messages[msg.id] = question
    except discord.HTTPException as exc:
        log.warning("Could not add reactions: %s", exc)


@client.tree.command(
    name="help",
    description="Learn what this bot does and how to use it",
)
async def help_cmd(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title="📖 PM Accelerator Knowledge Base Bot",
        description=(
            "I answer questions about the **PM Accelerator AI Engineering Internship** "
            "program using Retrieval-Augmented Generation (RAG).\n\n"
            "I search the official program documents and generate grounded answers — "
            "I will tell you when I don't have information rather than guess."
        ),
        color=BLURPLE,
    )
    embed.add_field(
        name="Commands",
        value=(
            "**`/ask <question>`** — Ask any question about the program\n"
            "**`/stats`** — View usage statistics\n"
            "**`/help`** — Show this message"
        ),
        inline=False,
    )
    embed.add_field(
        name="Feedback",
        value=(
            "After each answer, react with 👍 or 👎 to help improve the bot. "
            "Your feedback is recorded anonymously."
        ),
        inline=False,
    )
    embed.add_field(
        name="Source documents",
        value=(
            "• AI Bootcamp Journey & Learning Path\n"
            "• Training For AI Engineer Interns\n"
            "• Intern FAQ"
        ),
        inline=False,
    )
    embed.set_footer(text="Powered by Gemini 1.5 Flash + MongoDB Atlas Vector Search")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@client.tree.command(
    name="stats",
    description="View bot usage statistics",
)
async def stats_cmd(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        data = await get_stats()
    except Exception as exc:
        log.exception("Failed to fetch stats: %s", exc)
        await interaction.followup.send(
            embed=discord.Embed(
                title="❌ Error",
                description="Could not retrieve stats. Please try again.",
                color=RED,
            ),
            ephemeral=True,
        )
        return

    total = data.get("total_queries", 0)
    pos = data.get("positive_feedback", 0)
    neg = data.get("negative_feedback", 0)
    total_fb = data.get("total_feedback", 0)
    satisfaction = f"{pos / total_fb * 100:.0f}%" if total_fb > 0 else "N/A"

    embed = discord.Embed(title="📊 Bot Statistics", color=YELLOW)
    embed.add_field(name="Total Queries", value=str(total), inline=True)
    embed.add_field(name="Total Feedback", value=str(total_fb), inline=True)
    embed.add_field(name="Satisfaction", value=satisfaction, inline=True)
    embed.add_field(name="👍 Positive", value=str(pos), inline=True)
    embed.add_field(name="👎 Negative", value=str(neg), inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)


def main() -> None:
    client.run(os.environ["DISCORD_TOKEN"])


if __name__ == "__main__":
    main()
