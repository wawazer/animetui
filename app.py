from textual.app import App
from ui.screens import WelcomeScreen


class AnimeTUI(App):
    TITLE = "AnimeTUI"

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen())


def main() -> None:
    app = AnimeTUI()
    app.run()


if __name__ == "__main__":
    main()
