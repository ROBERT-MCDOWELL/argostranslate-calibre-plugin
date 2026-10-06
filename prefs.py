from calibre.utils.config import JSONConfig
prefs = JSONConfig('plugins/argos_translate')
prefs.defaults['device'] = 'cpu'
prefs.defaults['batch_size'] = 16
prefs.defaults['use_cache'] = True
prefs.defaults['auto_install'] = True
prefs.defaults['mode'] = 'replace'
prefs.defaults['src'] = ''
prefs.defaults['dst'] = 'en'
prefs.defaults['languages'] = {}
prefs.defaults['pairs'] = []
prefs.defaults['available'] = []
