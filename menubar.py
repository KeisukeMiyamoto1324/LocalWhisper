import rumps

class MenuBarApp(rumps.App):
    def __init__(self, name, show_window_callback, quit_callback):
        super(MenuBarApp, self).__init__(name, icon='icon.png') # アイコンファイルを別途用意
        self.show_window_callback = show_window_callback
        self.quit_callback = quit_callback
        self.menu = [
            rumps.MenuItem('Show Main Window', callback=self.show_window),
            None,
            rumps.MenuItem('Quit', callback=self.quit_app)
        ]

    def show_window(self, _):
        self.show_window_callback()

    def quit_app(self, _):
        self.quit_callback()
        rumps.quit_application()