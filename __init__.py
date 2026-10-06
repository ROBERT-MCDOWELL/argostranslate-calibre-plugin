from calibre.customize import InterfaceActionBase
class ArgosTranslatePlugin(InterfaceActionBase):
    name = 'Argos Translate'
    description = 'Translate EPUB/AZW3 books offline with Argos Translate'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'David'
    version = (26, 10, 1)
    minimum_calibre_version = (6, 0, 0)
    actual_plugin = 'calibre_plugins.argos_translate.ui:ArgosTranslateAction'
    def is_customizable(self)->bool:
        return True
    def config_widget(self):
        from calibre_plugins.argos_translate.config import ConfigWidget
        return ConfigWidget()
    def save_settings(self, config_widget)->None:
        config_widget.save_settings()
    def cli_main(self, args:list[str])->None:
        from calibre_plugins.argos_translate.cli import main
        argv = list(args)
        if argv and argv[0] == self.name:
            argv = argv[1:]
        raise SystemExit(main(argv))
