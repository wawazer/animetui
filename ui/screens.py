from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container, Horizontal, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from core.player import download_stream, play_stream
from core.scraper import extract_stream_url, get_episodes, search_content

ASCII_BANNER = """
   _    _   _ ___ __  __ _____ _____ _   _ ___ 
  / \\  | \\ | |_ _|  \\/  | ____|_   _| | | |_ _|
 / _ \\ |  \\| || || |\\/| |  _|   | | | | | || | 
/ ___ \\| |\\  || || |  | | |___  | | | |_| || | 
/_/   \\_\\_| \\_|___|_|  |_|_____| |_|  \\___/|___|
"""

CHANGELOG_TEXT = """[bold #c084fc]Feature Highlights[/bold #c084fc]

  [#10b981]• [Fixed][/] Providers & Stream Resolution
  [#10b981]• [Fixed][/] Kwik HLS Stream Decoders
  [#3b82f6]• [Added][/] Direct MPV Player & yt-dlp Integration
  [#9ca3af]• [System][/] Desktop User-Agent & Referer Bypass

[bold #8b5cf6]── [s] Search ── [q] Quit ──[/bold #8b5cf6]"""


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
                yield Static("Select an anime to inspect episodes", id="detail-card")
                yield OptionList(id="episodes-list")

        yield Static("Ready", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def set_status(self, text: str) -> None:
        status = self.query_one("#status-bar", Static)
        status.update(text)

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
        detail_card.update(f"[bold #c084fc]{title}[/]\nStatus: {status}\nLoading episodes...")
        self.fetch_episodes(self.active_anime["url"])

    @work(exclusive=True)
    async def fetch_episodes(self, url: str) -> None:
        self.set_status("Fetching episodes...")
        ep_widget = self.query_one("#episodes-list", OptionList)
        ep_widget.clear_options()

        self.episode_results = await get_episodes(url)
        detail_card = self.query_one("#detail-card", Static)

        if self.active_anime:
            title = self.active_anime.get("title", "")
            status = self.active_anime.get("status", "")
            detail_card.update(
                f"[bold #c084fc]{title}[/]\nStatus: {status}\nTotal Episodes: {len(self.episode_results)}"
            )

        if not self.episode_results:
            self.set_status("No episodes found.")
            return

        for idx, ep in enumerate(self.episode_results):
            date_info = f" ({ep['date']})" if ep.get("date") and ep["date"] != "N/A" else ""
            label = f"{ep['title']}{date_info}"
            ep_widget.add_option(Option(label, id=str(idx)))

        self.set_status(f"Loaded {len(self.episode_results)} episodes.")
        ep_widget.focus()

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

        stream_url, referer = await extract_stream_url(episode["url"])
        target_url = stream_url or episode["url"]

        if download:
            self.set_status(f"Starting download: {episode['title']}...")
            success, msg = download_stream(target_url, episode["title"], referer=referer)
        else:
            self.set_status(f"Launching MPV: {episode['title']}...")
            success, msg = play_stream(target_url, episode["title"], referer=referer)

        self.set_status(msg)
