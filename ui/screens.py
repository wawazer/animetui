import asyncio
from io import BytesIO

from rich.markup import escape
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container, Horizontal, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from core.player import download_stream, play_stream
from core.scraper import extract_stream_url, fetch_bytes, get_episodes, search_content

try:
    from PIL import Image, ImageOps
except ImportError:  # Pillow is optional; the poster URL is still shown.
    Image = None
    ImageOps = None

ASCII_BANNER = """
   _    _   _ ___ __  __ _____ _____ _   _ ___ 
  / \\  | \\ | |_ _|  \\/  | ____|_   _| | | |_ _|
 / _ \\ |  \\| || || |\\/| |  _|   | | | | | || | 
/ ___ \\| |\\  || || |  | | |___  | | | |_| || | 
/_/   \\_\\_| \\_|___|_|  |_|_____| |_|  \\___/|___|
"""

CHANGELOG_TEXT = """[bold #c084fc]Feature Highlights[/bold #c084fc]

  [#10b981]• [Fixed][/] Providers & Stream Resolution
  [#10b981]• [Fixed][/] Kwik & Blogger Stream Decoders
  [#3b82f6]• [Added][/] Poster / Thumbnail ASCII Preview
  [#3b82f6]• [Added][/] Direct MPV Player & yt-dlp Integration
  [#9ca3af]• [System][/] Desktop User-Agent & Referer Bypass

[bold #8b5cf6]── [s] Search ── [q] Quit ──[/bold #8b5cf6]"""

ASCII_RAMP = " .:-=+*#%@"


def render_ascii_image(data: bytes, max_width: int = 36, max_height: int = 10) -> str:
    """Convert image bytes to a compact grayscale ASCII poster."""
    if not data or Image is None:
        return ""

    try:
        image = Image.open(BytesIO(data)).convert("L")
    except Exception:
        return ""

    if image.width <= 0 or image.height <= 0:
        return ""

    aspect = image.height / image.width
    width = max_width
    height = max(1, int(width * aspect * 0.45))

    if height > max_height:
        height = max_height
        width = max(8, int(height / (aspect * 0.45)))

    image = image.resize((width, height))
    if ImageOps is not None:
        image = ImageOps.autocontrast(image)

    pixels = list(image.tobytes())
    lines = []
    for y in range(height):
        row = pixels[y * width:(y + 1) * width]
        lines.append("".join(ASCII_RAMP[p * (len(ASCII_RAMP) - 1) // 255] for p in row))

    return "\n".join(line.rstrip() for line in lines)


class WelcomeScreen(Screen):
    BINDINGS = [
        Binding("s", "open_search", "Search"),
        Binding("q", "app.quit", "Quit"),
        Binding("question_mark", "show_help", "Help"),
    ]

    CSS = """
    WelcomeScreen {
        background: #0d0d0d;
        align: center middle;
    }

    #welcome-container {
        width: 100%;
        height: 100%;
        align: center middle;
    }

    #banner-box {
        width: auto;
        height: auto;
        color: #8b5cf6;
        text-style: bold;
        content-align: center middle;
        margin-bottom: 0;
    }

    #version-label {
        width: 100%;
        text-align: center;
        color: #9ca3af;
        margin-bottom: 1;
    }

    #news-box {
        width: 65;
        height: 14;
        border: round #8b5cf6;
        background: #141414;
        color: #e5e7eb;
        padding: 1 2;
        content-align: center middle;
        text-align: center;
    }

    #welcome-footer {
        dock: bottom;
        height: 1;
        background: #111827;
        color: #9ca3af;
        text-align: center;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="welcome-container"):
            with Middle():
                with Center():
                    yield Static(ASCII_BANNER, id="banner-box")
                    yield Label("v0.1.0", id="version-label")
                    yield Static(CHANGELOG_TEXT, id="news-box")
        yield Static("[s] Search   [?] Help   [q] Quit", id="welcome-footer")
        yield Footer()

    def action_open_search(self) -> None:
        self.app.push_screen(SearchScreen())

    def action_show_help(self) -> None:
        news_box = self.query_one("#news-box", Static)
        news_box.update(
            "[bold #c084fc]Help & Navigation[/bold #c084fc]\n\n"
            "  [#e5e7eb]Press [s] to open Search\n"
            "  Press [p] to play in MPV\n"
            "  Press [d] to download via yt-dlp\n"
            "  Press [Esc/b] to return\n\n"
            "[bold #8b5cf6]── [s] Search ── [q] Quit ──[/bold #8b5cf6]"
        )


class SearchScreen(Screen):
    BINDINGS = [
        Binding("q", "app.quit", "Quit"),
        Binding("s", "focus_search", "Search"),
        Binding("p", "play_selected", "Play"),
        Binding("d", "download_selected", "Download"),
        Binding("escape", "go_back", "Back"),
        Binding("b", "go_back", "Back"),
    ]

    CSS = """
    SearchScreen {
        background: #0d0d0d;
    }

    #search-box {
        dock: top;
        height: 3;
        margin: 1 1 0 1;
    }

    #search-input {
        border: round #8b5cf6;
        background: #141414;
        color: #f3f4f6;
    }

    #search-input:focus {
        border: round #c084fc;
    }

    #main-container {
        height: 1fr;
        margin: 0 1;
    }

    .column {
        width: 1fr;
        height: 1fr;
        border: round #8b5cf6;
        background: #141414;
        padding: 0 1;
        margin: 0 1;
    }

    .column-title {
        text-style: bold;
        color: #c084fc;
        padding-bottom: 1;
    }

    #poster-preview {
        width: 100%;
        height: 12;
        border: round #374151;
        background: #0b0b0b;
        color: #e5e7eb;
        content-align: center middle;
        text-align: center;
        margin-bottom: 1;
    }

    #detail-card {
        height: 6;
        border-bottom: solid #374151;
        color: #d1d5db;
        padding-bottom: 1;
        margin-bottom: 1;
    }

    OptionList {
        height: 1fr;
        background: transparent;
        border: none;
        color: #e5e7eb;
    }

    OptionList:focus {
        border: none;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: #1f1b2e;
        color: #c084fc;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.search_results: list[dict] = []
        self.episode_results: list[dict] = []
        self.active_anime: dict | None = None
        self._poster_cache: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="search-box"):
            yield Input(placeholder="Search anime... (Press Enter)", id="search-input")

        with Horizontal(id="main-container"):
            with Vertical(classes="column"):
                yield Label("Search Results", classes="column-title")
                yield OptionList(id="results-list")

            with Vertical(classes="column"):
                yield Label("Anime Details & Episodes", classes="column-title")
                yield Static("Poster preview", id="poster-preview")
                yield Static("Select an anime to inspect episodes", id="detail-card")
                yield OptionList(id="episodes-list")

        yield Static("Ready", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def set_status(self, text: str) -> None:
        status = self.query_one("#status-bar", Static)
        status.update(text)

    def _update_poster(self, content: str) -> None:
        try:
            self.query_one("#poster-preview", Static).update(content)
        except Exception:
            pass

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if query:
            self.run_search(query)

    @work(exclusive=True)
    async def run_search(self, query: str) -> None:
        self.set_status(f"Searching: {query}...")
        results_widget = self.query_one("#results-list", OptionList)
        results_widget.clear_options()

        self.search_results = await search_content(query)
        if not self.search_results:
            self.set_status("No results found.")
            return

        for idx, item in enumerate(self.search_results):
            label = f"{item['title']} [{item.get('status', 'N/A')}]"
            results_widget.add_option(Option(label, id=str(idx)))

        self.set_status(f"Found {len(self.search_results)} items.")
        results_widget.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "results-list":
            index = int(event.option_id)
            if 0 <= index < len(self.search_results):
                self.active_anime = self.search_results[index]
                self.load_episodes_for_active()
        elif event.option_list.id == "episodes-list":
            self.action_play_selected()

    def load_episodes_for_active(self) -> None:
        if not self.active_anime:
            return

        detail_card = self.query_one("#detail-card", Static)
        title = self.active_anime.get("title", "")
        status = self.active_anime.get("status", "")
        thumbnail = self.active_anime.get("thumbnail", "")
        detail_card.update(
            f"[bold #c084fc]{title}[/]\n"
            f"Status: {status}\n"
            f"Poster: {thumbnail or 'N/A'}\n"
            "Loading episodes..."
        )
        self._update_poster(
            "[dim]Loading poster preview...[/dim]" if thumbnail else "[dim]No poster available[/dim]"
        )
        self.fetch_episodes(self.active_anime["url"])

    async def show_poster(self, thumbnail_url: str) -> None:
        if not thumbnail_url:
            self._update_poster("[dim]No poster available[/dim]")
            return

        cached = self._poster_cache.get(thumbnail_url)
        if cached is not None:
            self._update_poster(cached or f"[dim]{escape(thumbnail_url)}[/dim]")
            return

        self._update_poster("[dim]Loading poster preview...[/dim]")
        referer = self.active_anime.get("url") if self.active_anime else None
        data = await fetch_bytes(thumbnail_url, referer=referer)
        art = await asyncio.to_thread(render_ascii_image, data) if data else ""
        self._poster_cache[thumbnail_url] = art
        self._update_poster(art or f"[dim]{escape(thumbnail_url)}[/dim]")

    @work(exclusive=True)
    async def fetch_episodes(self, url: str) -> None:
        self.set_status("Fetching episodes...")
        ep_widget = self.query_one("#episodes-list", OptionList)
        ep_widget.clear_options()

        self.episode_results = await get_episodes(url)
        detail_card = self.query_one("#detail-card", Static)

        title = self.active_anime.get("title", "") if self.active_anime else ""
        status = self.active_anime.get("status", "") if self.active_anime else ""
        thumbnail = self.active_anime.get("thumbnail", "") if self.active_anime else ""
        if not thumbnail:
            thumbnail = next(
                (ep.get("thumbnail", "") for ep in self.episode_results if ep.get("thumbnail")),
                "",
            )

        detail_card.update(
            f"[bold #c084fc]{title}[/]\n"
            f"Status: {status}\n"
            f"Total Episodes: {len(self.episode_results)}\n"
            f"Poster: {thumbnail or 'N/A'}"
        )
        if not self.episode_results:
            self.set_status("No episodes found.")
            await self.show_poster(thumbnail)
            return

        for idx, ep in enumerate(self.episode_results):
            date_info = f" ({ep['date']})" if ep.get("date") and ep["date"] != "N/A" else ""
            label = f"{ep['title']}{date_info}"
            ep_widget.add_option(Option(label, id=str(idx)))

        self.set_status(f"Loaded {len(self.episode_results)} episodes.")
        ep_widget.focus()
        await self.show_poster(thumbnail)

    def get_selected_episode(self) -> dict | None:
        ep_widget = self.query_one("#episodes-list", OptionList)
        idx = ep_widget.highlighted
        if idx is not None and 0 <= idx < len(self.episode_results):
            return self.episode_results[idx]
        return None

    def action_play_selected(self) -> None:
        episode = self.get_selected_episode()
        if not episode:
            self.set_status("No episode selected.")
            return
        self.trigger_stream_action(episode, download=False)

    def action_download_selected(self) -> None:
        episode = self.get_selected_episode()
        if not episode:
            self.set_status("No episode selected.")
            return
        self.trigger_stream_action(episode, download=True)

    @work(exclusive=True)
    async def trigger_stream_action(self, episode: dict, download: bool = False) -> None:
        action_verb = "Downloading" if download else "Resolving stream"
        self.set_status(f"{action_verb}: {episode['title']}...")

        selected_episode_url = episode["url"]
        res = await extract_stream_url(selected_episode_url)
        if isinstance(res, tuple):
            stream_url, referer_url = res
        else:
            stream_url, referer_url = res, selected_episode_url

        if stream_url and stream_url.startswith("//"):
            stream_url = "https:" + stream_url

        if not stream_url:
            self.set_status(f"Could not resolve a playable stream for: {episode['title']}")
            return

        referer_url = referer_url or selected_episode_url

        if download:
            self.set_status(f"Starting download: {episode['title']}...")
            success, msg = download_stream(stream_url, episode["title"], referer=referer_url)
        else:
            self.set_status(f"Launching MPV: {episode['title']}...")
            success, msg = play_stream(stream_url, referer_url, episode["title"])

        self.set_status(msg)
